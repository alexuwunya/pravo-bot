import os
from gtts import gTTS
import uuid
import logging

logger = logging.getLogger(__name__)


async def generate_voice_message(text: str) -> str:
    try:
        # Удаляем Markdown символы, чтобы бот не читал "звездочка"
        clean_text = text.replace('*', '').replace('_', '').replace('`', '')

        # Генерируем уникальное имя файла
        filename = f"temp_voice_{uuid.uuid4()}.mp3"

        # Создаем аудио (lang='ru' для русского языка)
        tts = gTTS(text=clean_text, lang='ru')
        tts.save(filename)

        return filename
    except Exception as e:
        logger.error(f"Ошибка генерации TTS: {e}")
        return None


def cleanup_voice_file(filename: str):
    if filename and os.path.exists(filename):
        os.remove(filename)