import os
import logging
from aiogram import Bot
from aiogram.types import Message
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = AsyncGroq(api_key=GROQ_API_KEY)


async def handle_voice_message(bot: Bot, message: Message) -> str:

    file_path = None
    try:
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        file_path = f"temp_voice_{file_id}.ogg"

        await bot.download_file(file.file_path, file_path)

        with open(file_path, "rb") as audio_file:
            transcription = await groq_client.audio.transcriptions.create(
                file=(file_path, audio_file.read()),
                model="whisper-large-v3",
                language="ru",
                response_format="json"
            )

        text = transcription.text.strip()
        logger.info(f"🎙 Распознано: {text}")
        return text

    except Exception as e:
        logger.error(f"❌ Ошибка STT: {e}")
        return None
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Ошибка удаления файла {file_path}: {e}")