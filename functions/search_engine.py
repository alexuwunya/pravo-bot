import logging
import asyncio
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State  # Импортируем State напрямую, StatesGroup не нужен
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from ragsystem import RAGSystem
from databases.settings_db import settings_db
from functions.tts_utils import generate_voice_message, cleanup_voice_file

logger = logging.getLogger(__name__)


class LegalSearchEngine:
    def __init__(self, router: Router, db_instance, doc_name: str, collection_name: str):
        self.router = router
        self.db = db_instance
        self.doc_name = doc_name
        self.collection_name = collection_name
        self.rag = None
        self._init_lock = asyncio.Lock()

        # 🔥 ИСПРАВЛЕНИЕ: Генерируем уникальный стейт для каждого движка
        # Имя стейта будет уникальным: "waiting_constitution", "waiting_child_rights" и т.д.
        self.waiting_state = State(state=f"waiting_{collection_name}")

    async def get_rag(self):
        """Ленивая инициализация RAG"""
        if self.rag:
            return self.rag

        async with self._init_lock:
            if self.rag: return self.rag

            # Проверяем, есть ли данные. Если нет - пробуем загрузить.
            if not self.db.is_loaded():
                logger.info(f"📥 База {self.doc_name} пуста/не найдена. Запускаю парсинг...")
                success = await self.db.update_from_source()
                if not success:
                    logger.error(f"❌ Не удалось обновить базу {self.doc_name}")
                    return None

            text = self.db.get_text()
            if not text:
                logger.warning(f"⚠️ Текст для {self.doc_name} пуст после загрузки.")
                return None

            try:
                rag = RAGSystem(text, self.collection_name, self.doc_name)
                await rag.initialize()
                self.rag = rag
                return self.rag
            except Exception as e:
                logger.error(f"RAG Init Error ({self.doc_name}): {e}")
                return None

    def register_handlers(self, trigger_callback: str):

        # 1. Вход в режим поиска
        @self.router.callback_query(F.data == trigger_callback)
        async def start_search_handler(callback: types.CallbackQuery, state: FSMContext):
            await callback.message.edit_text(
                f'🔍 Поиск по документу: "{self.doc_name}"\n\nВведите ваш вопрос или ключевые слова:',
                reply_markup=self._get_back_button()
            )
            # Устанавливаем УНИКАЛЬНОЕ состояние этого движка
            await state.set_state(self.waiting_state)
            await callback.answer()

        # 2. Обработка вопроса (Фильтруем по УНИКАЛЬНОМУ состоянию)
        @self.router.message(self.waiting_state)
        async def process_query_handler(message: types.Message, state: FSMContext):
            # Проверка active_engine больше не нужна, так как state уникален

            query = message.text.strip()
            if not query:
                await message.answer("Пожалуйста, введите текст вопроса.")
                return

            wait_msg = await message.answer(f"🤔 Ищу ответ в: {self.doc_name}...")

            rag = await self.get_rag()
            if not rag:
                await wait_msg.edit_text("❌ Ошибка: база данных не загружена или пуста.")
                return

            answer = await rag.answer_question(query)

            await wait_msg.delete()

            response_text = f"📜 **{self.doc_name}**\n\n{answer}"
            if len(response_text) > 4000: response_text = response_text[:4000] + "..."

            await message.answer(
                response_text,
                parse_mode="Markdown",
                reply_markup=self._get_back_button()
            )

            # TTS
            user_id = message.from_user.id
            if settings_db.get_voice_setting(user_id):
                voice_file = await generate_voice_message(answer)
                if voice_file:
                    try:
                        audio = FSInputFile(voice_file)
                        await message.answer_voice(voice=audio, caption="🎧 Озвученный ответ")
                    except Exception as e:
                        logger.error(f"TTS Error: {e}")
                    finally:
                        cleanup_voice_file(voice_file)

            await state.clear()

    def _get_back_button(self):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_main_menu')]
        ])