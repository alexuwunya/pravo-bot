import logging
import asyncio
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from ragsystem import RAGSystem
from databases.settings_db import settings_db
from functions.tts_utils import generate_voice_message, cleanup_voice_file

from functions.stt_utils import handle_voice_message

logger = logging.getLogger(__name__)


class LegalSearchEngine:
    def __init__(self, router: Router, db_instance, doc_name: str, collection_name: str):
        self.router = router
        self.db = db_instance
        self.doc_name = doc_name
        self.collection_name = collection_name
        self.rag = None
        self._init_lock = asyncio.Lock()

        self.waiting_state = State(state=f"waiting_{collection_name}")

    async def get_rag(self):
        if self.rag:
            return self.rag

        async with self._init_lock:
            if self.rag: return self.rag

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

        @self.router.callback_query(F.data == trigger_callback)
        async def start_search_handler(callback: types.CallbackQuery, state: FSMContext):
            await callback.message.edit_text(
                f'🔍 Поиск по документу: "{self.doc_name}"\n\n'
                f'Введите ваш вопрос текстом'
                f'{" или запишите голосовое сообщение 🎙" if settings_db.get_voice_input_setting(callback.from_user.id) else ""}:',
                reply_markup=self._get_back_button()
            )
            await state.set_state(self.waiting_state)
            await callback.answer()

        @self.router.message(self.waiting_state, F.text | F.voice)
        async def process_query_handler(message: types.Message, state: FSMContext):
            user_id = message.from_user.id
            query = ""

            if message.voice:
                if not settings_db.get_voice_input_setting(user_id):
                    await message.answer(
                        "⚠️ Голосовой ввод отключен в настройках. Пожалуйста, напишите вопрос текстом или включите опцию в меню.")
                    return

                processing_msg = await message.answer("👂 Слушаю и распознаю вопрос...")

                query = await handle_voice_message(message.bot, message)

                if not query:
                    await processing_msg.edit_text(
                        "❌ Не удалось распознать речь. Попробуйте еще раз или напишите текстом.")
                    return

                await processing_msg.edit_text(f"🗣 Вы спросили: *{query}*", parse_mode="Markdown")
            else:
                query = message.text.strip()

            if not query:
                await message.answer("Пожалуйста, введите текст вопроса.")
                return

            data = await state.get_data()
            last_voice_id = data.get('last_voice_id')
            if last_voice_id:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=last_voice_id)
                except:
                    pass

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

            if settings_db.get_voice_setting(user_id):
                voice_file = await generate_voice_message(answer)
                if voice_file:
                    try:
                        audio = FSInputFile(voice_file)
                        voice_msg = await message.answer_voice(voice=audio, caption="🎧 Озвученный ответ")
                        await state.update_data(last_voice_id=voice_msg.message_id)
                    except Exception as e:
                        logger.error(f"TTS Error: {e}")
                    finally:
                        cleanup_voice_file(voice_file)

    def _get_back_button(self):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🔙 Назад в меню', callback_data='back_main_menu')]
        ])