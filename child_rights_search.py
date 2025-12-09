from aiogram import Bot, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
from databases.childrights_db import child_rights_db, initialize_child_rights_law
from ragsystem import LegalRAGSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8570949555:AAEd_1zDKV3F_7gNG5wsl_gnbYa9-dqRyI8'

bot = Bot(token=BOT_TOKEN)

child_rights_search_router = Router()
child_rights_rag = None


async def initialize_child_rights_rag_system():
    global child_rights_rag
    try:
        if not child_rights_db.is_law_loaded():
            logger.info("🔄 Закон не загружен в БД, запускаю загрузку...")
            initialize_child_rights_law()

        law_text = child_rights_db.get_law_text()
        if not law_text:
            logger.error("❌ Не удалось получить текст закона из БД")
            return False

        logger.info(f"📖 Текст закона о правах ребенка получен, длина: {len(law_text)} символов")

        required_keywords = ["правах ребенка", "ребенок", "несовершеннолетн"]
        forbidden_keywords = ["Конституция", "Республика Беларусь"]

        has_required = any(keyword in law_text.lower() for keyword in required_keywords)
        has_forbidden = any(keyword in law_text for keyword in forbidden_keywords)

        if not has_required:
            logger.error("❌ Полученный текст не содержит ключевых слов закона о правах ребенка!")
            return False

        if has_forbidden:
            logger.error("❌ В тексте закона найден текст Конституции!")
            return False

        child_rights_rag = LegalRAGSystem(law_text, "Закон о правах ребенка")
        logger.info(
            f"✅ RAGSystem для закона о правах ребенка инициализирована. Коллекция: {child_rights_rag.collection_name}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации RAG системы для закона о правах ребенка: {e}")
        return False


@child_rights_search_router.startup()
async def on_startup():
    """Запускается при старте бота"""
    logger.info("🔄 Инициализация системы для закона о правах ребенка...")
    success = await initialize_child_rights_rag_system()
    if success:
        logger.info("✅ Система для закона о правах ребенка успешно инициализирована")
    else:
        logger.error("❌ Не удалось инициализировать систему для закона о правах ребенка")


class ChildRightsSearch(StatesGroup):
    waiting_for_keyword = State()


@child_rights_search_router.callback_query(F.data == 'act_child_rights')
async def act_child_rights_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text='🔍 Поиск в законе "О правах ребенка"\n\nВведите ваш вопрос или ключевые слова для поиска...',
        reply_markup=get_back_button()
    )
    await state.set_state(ChildRightsSearch.waiting_for_keyword)
    await callback.answer()


@child_rights_search_router.message(ChildRightsSearch.waiting_for_keyword)
async def process_child_rights_keyword(message: types.Message, state: FSMContext):
    keyword = message.text.strip()

    if not keyword:
        await message.answer("❌ Пожалуйста, введите вопрос или ключевые слова для поиска.")
        return

    if child_rights_rag is None:
        await message.answer("📥 Загружаю актуальную версию закона...")
        success = await initialize_child_rights_rag_system()
        if not success or child_rights_rag is None:
            await message.answer(
                "❌ Не удалось загрузить закон. Попробуйте позже.",
                reply_markup=get_back_button()
            )
            await state.clear()
            return

    await message.answer("🤔 Анализирую ваш запрос\nИщу информацию в тексте закона...")

    try:
        message_text = await child_rights_rag.answer_question(keyword)
    except Exception as e:
        logger.error(f"Ошибка при поиске в законе о правах ребенка: {e}")
        message_text = "❌ Произошла ошибка при поиске. Попробуйте позже."

    if not message_text or len(message_text.strip()) < 10:
        message_text = "❌ По вашему запросу не найдено конкретной информации в законе. Попробуйте переформулировать вопрос."

    response_text = f"📜 Результат поиска по закону 'О правах ребенка':\n\n{message_text}"

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