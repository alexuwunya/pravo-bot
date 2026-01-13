import os
from gtts import gTTS
import uuid
import logging

logger = logging.getLogger(__name__)


async def generate_voice_message(text: str) -> str:
    try:
        clean_text = text.replace('*', '').replace('_', '').replace('`', '')

        filename = f"temp_voice_{uuid.uuid4()}.mp3"

        tts = gTTS(text=clean_text, lang='ru')
        tts.save(filename)

        return filename
    except Exception as e:
        logger.error(f"Ошибка генерации TTS: {e}")
        return None


def cleanup_voice_file(filename: str):
    if filename and os.path.exists(filename):
        os.remove(filename)