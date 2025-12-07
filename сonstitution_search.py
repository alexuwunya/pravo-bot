from aiogram import Bot, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
from bs4 import BeautifulSoup
import logging
import re
from databases.database_constitution import constitution_db
from ragsystem import RAGSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)

constitution_search_router = Router()
constitution_rag = None

async def initialize_rag_system():
    global constitution_rag
    try:
        if not constitution_db.is_constitution_loaded():
            logger.warning("Конституция не загружена в БД")
            return False

        constitution_text = constitution_db.get_constitution_text()
        if not constitution_text:
            logger.error("Не удалось получить текст Конституции из БД")
            return False

        logger.info(f"📖 Текст Конституции получен, длина: {len(constitution_text)} символов")

        # Улучшенная валидация текста
        required_keywords = ["Конституция", "Республика Беларусь"]
        forbidden_keywords = ["О правах ребенка"]

        has_required = any(keyword in constitution_text for keyword in required_keywords)
        has_forbidden = any(keyword in constitution_text for keyword in forbidden_keywords)

        if not has_required:
            logger.error("Текст не содержит обязательных ключевых слов Конституции")
            return False

        if has_forbidden:
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: В тексте Конституции найден текст о правах ребенка!")
            # Очищаем базу и перезагружаем
            constitution_db.clear_database()
            await parse_and_save_constitution()
            return await initialize_rag_system()

        constitution_rag = RAGSystem(constitution_text, "constitution_articles", "Конституция Республики Беларусь")
        logger.info(f"✅ RAGSystem для Конституции инициализирована. Коллекция: {constitution_rag.collection_name}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации RAG системы для Конституции: {e}")
        return False

@constitution_search_router.startup()
async def on_startup():
    """Запускается при старте бота"""
    try:
        if not constitution_db.is_constitution_loaded():
            logger.info("Конституция не найдена в БД. Запускаю первоначальную загрузку...")
            result = await parse_and_save_constitution()
            if not result['success']:
                logger.error(f"Ошибка загрузки Конституции при старте: {result['error']}")
                return

        success = await initialize_rag_system()
        if not success:
            logger.error("Не удалось инициализировать RAG систему для Конституции")
        else:
            logger.info("✅ RAG система для Конституции готова к работе")

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске ConstitutionSearch: {e}")

class Operation(StatesGroup):
    waiting_for_keyword = State()

async def parse_etalonline_by_document():
    """Парсит Конституцию с сайта etalonline.by"""
    try:
        url = "https://etalonline.by/document/?regnum=v19402875&q_id=2524604"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        logger.info(f"🔄 Начинаю парсинг Конституции с {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        section_element = soup.find('div', class_='Section1')

        if not section_element:
            logger.error("Элемент с классом Section1 не найден на странице")
            return {'success': False, 'error': 'Структура страницы изменилась'}

        all_text = section_element.get_text(separator=' ', strip=True)
        cleaned_text = re.sub(r'\s+', ' ', all_text).strip()

        # Валидация полученного текста
        required_keywords = ["Конституция", "Республика Беларусь"]
        forbidden_keywords = ["О правах ребенка"]

        has_required = any(keyword in cleaned_text for keyword in required_keywords)
        has_forbidden = any(keyword in cleaned_text for keyword in forbidden_keywords)

        if not has_required:
            return {
                'success': False,
                'error': 'Полученный текст не является валидной Конституцией Республики Беларусь'
            }

        if has_forbidden:
            return {
                'success': False,
                'error': 'ОШИБКА: Получен текст закона о правах ребенка вместо Конституции'
            }

        logger.info(f"✅ Конституция успешно распарсена, длина: {len(cleaned_text)} символов")
        return {
            'success': True,
            'text': cleaned_text,
            'url': url
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка подключения при парсинге Конституции: {e}")
        return {'success': False, 'error': f'Ошибка подключения: {str(e)}'}
    except Exception as e:
        logger.error(f"Неожиданная ошибка при парсинге Конституции: {e}")
        return {'success': False, 'error': f'Ошибка парсинга: {str(e)}'}

@constitution_search_router.callback_query(F.data == 'konstitution_search')
async def konstitution_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text='🔍 Поиск в Конституции\n\nВведите ваш вопрос или ключевые слова для поиска в тексте Конституции...',
        reply_markup=get_back_button()
    )
    await state.set_state(Operation.waiting_for_keyword)
    await callback.answer()

@constitution_search_router.message(Operation.waiting_for_keyword)
async def process_keyword(message: types.Message, state: FSMContext):
    keyword = message.text.strip()

    if not keyword:
        await message.answer("❌ Пожалуйста, введите вопрос или ключевые слова для поиска.")
        return

    if constitution_rag is None:
        await message.answer("📥 Загружаю актуальную версию Конституции...")
        success = await initialize_rag_system()
        if not success:
            await message.answer(
                "❌ Не удалось загрузить Конституцию. Попробуйте позже.",
                reply_markup=get_back_button()
            )
            await state.clear()
            return

    await message.answer("🤔 Анализирую ваш запрос\nИщу информацию в тексте Конституции...")

    try:
        message_text = constitution_rag.answer_question(keyword)
    except Exception as e:
        logger.error(f"Ошибка при поиске в Конституции: {e}")
        message_text = "❌ Произошла ошибка при поиске. Попробуйте позже."

    if not message_text or len(message_text.strip()) < 10:
        message_text = "❌ По вашему запросу не найдено конкретной информации в Конституции. Попробуйте переформулировать вопрос."

    response_text = f"📜 Результат поиска по Конституции:\n\n{message_text}"

    await message.answer(
        truncate_text(response_text),
        reply_markup=get_back_button()
    )

    await state.clear()

def truncate_text(text, max_length=4000):
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_main_menu')]
    ])

async def parse_and_save_constitution():
    """Парсит и сохраняет Конституцию в базу данных"""
    try:
        result = await parse_etalonline_by_document()
        if result['success']:
            constitution_db.save_constitution(result['text'], result['url'])
            logger.info("✅ Конституция успешно сохранена в базу данных")
            return {'success': True, 'message': 'Конституция успешно сохранена!'}
        else:
            return {'success': False, 'error': result['error']}
    except Exception as e:
        logger.error(f"Ошибка при сохранении Конституции в БД: {e}")
        return {'success': False, 'error': f'Ошибка сохранения: {str(e)}'}