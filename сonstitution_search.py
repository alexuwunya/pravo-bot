from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import requests
from bs4 import BeautifulSoup
import logging
import re
from database import constitution_db
from ragsystem import RAGSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8570949555:AAEd_1zDKV3F_7gNG5wsl_gnbYa9-dqRyI8'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()

constitution_search_router = Router()


@constitution_search_router.startup()
async def on_startup():
    """Автоматически загружает Конституцию в БД при старте, если она еще не загружена"""
    if not constitution_db.is_constitution_loaded():
        logger.info("Конституция не найдена в БД. Запускаю первоначальную загрузку...")
        result = await parse_and_save_constitution()
        if result['success']:
            logger.info("Конституция успешно загружена в БД при старте")
        else:
            logger.error(f"Ошибка загрузки Конституции при старте: {result['error']}")


class Operation(StatesGroup):
    waiting_for_keyword = State()


async def parse_etalonline_by_document():
    try:
        url = f"https://etalonline.by/document/?regnum=v19302570&q_id=4416393"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        section_element = soup.find('div', class_='Section1')

        if section_element:
            # Получаем весь текст с пробелами между элементами
            all_text = section_element.get_text(separator=' ', strip=True)

            # Очищаем текст от лишних пробелов
            cleaned_text = re.sub(r'\s+', ' ', all_text).strip()

            return {
                'success': True,
                'text': cleaned_text,
                'url': url
            }
        else:
            return {
                'success': False,
                'error': 'Элемент с классом Section1 не найден на странице'
            }

    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'Ошибка подключения к сайту: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Ошибка при парсинге: {str(e)}'
        }

@constitution_search_router.callback_query(F.data == 'konstitution_search')
async def konstitution_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text='🔍 Поиск в Конституции\n\nВведите ваш вопрос или ключевые слова для поиска в тексте Конституции...',
        reply_markup=get_back_button()
    )
    await state.set_state(Operation.waiting_for_keyword)


def truncate_text(text, max_length=4000):
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


@constitution_search_router.message(Operation.waiting_for_keyword)
async def process_keyword(message: types.Message, state: FSMContext):
    keyword = message.text.strip()

    if not keyword:
        await message.answer("❌ Пожалуйста, введите вопрос или ключевые слова для поиска.")
        return

    if not constitution_db.is_constitution_loaded():
        await message.answer("📥 Загружаю актуальную версию Конституции...")

        result = await parse_and_save_constitution()
        if not result['success']:
            await message.answer(
                f"❌ Ошибка загрузки Конституции: {result['error']}",
                reply_markup=get_back_button()
            )
            await state.clear()
            return

    await message.answer("🤔 Анализирую ваш запрос\nИщу информацию в тексте Конституции...")

    constitution_text = constitution_db.get_constitution_text()
    constitution_rag = RAGSystem(constitution_text)
    message_text = constitution_rag.answer_question(keyword)

    if not message_text or len(message_text.strip()) < 10:
        message_text = "❌ По вашему запросу не найдено конкретной информации в Конституции. Попробуйте переформулировать вопрос."

    response_text = f"📜 Результат поиска по Конституции:\n\n{message_text}"

    await message.answer(
        truncate_text(response_text),
        reply_markup=get_back_button(),
        parse_mode="Markdown"
    )

    await state.clear()


def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_main_menu')]
    ])


@constitution_search_router.callback_query(F.data == "init_constitution_db")
async def init_constitution_db(callback: types.CallbackQuery):
    await callback.message.answer("🔄 Обновляю базу данных Конституции...")

    result = await parse_and_save_constitution()

    if result['success']:
        info = constitution_db.get_constitution_info()
        if info:
            message = (
                f"✅ Конституция успешно обновлена!\n\n"
                f"📊 Проиндексировано разделов: {info['sentence_count']}\n"
                f"🕐 Последнее обновление: {info['last_updated']}"
            )
        else:
            message = "✅ Конституция успешно загружена в базу данных!"
        await callback.message.answer(message)
    else:
        await callback.message.answer(f"❌ Ошибка загрузки: {result['error']}")


async def parse_and_save_constitution():
    """Парсит и сохраняет Конституцию в базу данных"""
    result = await parse_etalonline_by_document()

    if result['success']:
        constitution_db.save_constitution(result['text'], result['url'])
        return {
            'success': True,
            'message': 'Конституция успешно сохранена в базу данных!'
        }
    else:
        return {
            'success': False,
            'error': result['error']
        }