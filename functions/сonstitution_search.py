import logging
import re
import asyncio
import aiohttp  # Используем асинхронный клиент
from aiogram import Bot, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bs4 import BeautifulSoup

from databases.database_constitution import constitution_db
from ragsystem import RAGSystem

logger = logging.getLogger(__name__)

constitution_search_router = Router()
constitution_rag = None


async def parse_etalonline_by_document():
    url = "https://etalonline.by/document/?regnum=v19402875&q_id=2524604"
    headers = {'User-Agent': 'Mozilla/5.0 ...'}  # Сократил для примера

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    return {'success': False, 'error': f'HTTP {response.status}'}
                content = await response.read()

        soup = BeautifulSoup(content, 'html.parser')
        # ... (логика парсинга HTML остается той же) ...
        # Упростим для примера, предполагая, что логика парсинга верна:
        section_element = soup.find('div', class_='Section1') or soup.find('div', class_='text')  # Добавил fallback

        if not section_element:
            # Попытка взять весь текст если секция не найдена
            cleaned_text = soup.get_text(separator=' ', strip=True)
        else:
            cleaned_text = re.sub(r'\s+', ' ', section_element.get_text(separator=' ', strip=True)).strip()

        # Валидация
        if "Конституция" not in cleaned_text:
            return {'success': False, 'error': 'Невалидный текст (нет слова Конституция)'}

        return {'success': True, 'text': cleaned_text, 'url': url}

    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return {'success': False, 'error': str(e)}


async def initialize_rag_system():
    global constitution_rag
    if constitution_rag is not None:
        return True

    text = constitution_db.get_constitution_text()
    if not text:
        logger.info("Загрузка текста с сайта...")
        res = await parse_etalonline_by_document()
        if res['success']:
            constitution_db.save_constitution(res['text'], res['url'])
            text = res['text']
        else:
            logger.error(f"Не удалось скачать: {res['error']}")
            return False

    try:
        constitution_rag = RAGSystem(text, "constitution_articles", "Конституция Республики Беларусь")
        return True
    except Exception as e:
        logger.error(f"RAG Init Error: {e}")
        return False


@constitution_search_router.startup()
async def on_startup():
    """Фоновая инициализация при старте"""
    asyncio.create_task(initialize_rag_system())


class ConstitutionState(StatesGroup):
    waiting_for_keyword = State()


def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_main_menu')]
    ])


@constitution_search_router.callback_query(F.data == 'konstitution_search')
async def start_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        '🔍 Поиск в Конституции\nВведите ваш вопрос:',
        reply_markup=get_back_button()
    )
    await state.set_state(ConstitutionState.waiting_for_keyword)
    await callback.answer()


@constitution_search_router.message(ConstitutionState.waiting_for_keyword)
async def process_question(message: types.Message, state: FSMContext):
    query = message.text.strip()
    if not query:
        await message.answer("Введите текст запроса.")
        return

    if not constitution_rag:
        msg = await message.answer("⏳ Система инициализируется, подождите...")
        success = await initialize_rag_system()
        if not success:
            await msg.edit_text("❌ Ошибка загрузки базы знаний.")
            return
        await msg.delete()

    wait_msg = await message.answer("🤔 Ищу ответ в Конституции...")

    answer = await constitution_rag.answer_question(query)

    await wait_msg.delete()
    await message.answer(
        f"📜 **Ответ:**\n\n{answer}",
        parse_mode="Markdown",
        reply_markup=get_back_button()
    )
    await state.clear()