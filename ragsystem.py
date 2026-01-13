import os
import re
import logging
import asyncio
from sentence_transformers import SentenceTransformer
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_manager import qdrant_manager
from groq import AsyncGroq

logger = logging.getLogger(__name__)

class ModelManager:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            logger.info("🔧 Загружаю модель SentenceTransformer (может занять время)...")
            try:
                cls._model = SentenceTransformer("intfloat/multilingual-e5-large")
                logger.info("✅ Модель SentenceTransformer загружена")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки модели: {e}")
                raise
        return cls._model


class RAGSystem:
    def __init__(self, paragraph: str, collection_name: str, document_name: str):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ GROQ_API_KEY не найден!")

        self.client = qdrant_manager.get_client()
        self.groq_client = AsyncGroq(api_key=self.api_key)
        self.llm_model = "llama-3.3-70b-versatile"
        self.codex = paragraph
        self.document_name = document_name

        safe_suffix = re.sub(r'[^a-zA-Z0-9_]', '', collection_name.lower().replace(' ', '_'))
        self.collection_name = f"legal_docs_{safe_suffix}" if not collection_name.startswith(
            "legal_") else collection_name

        self.model = None

    async def initialize(self):
        logger.info(f"🔍 Init RAG для: {self.document_name}, Коллекция: {self.collection_name}")
        loop = asyncio.get_running_loop()
        self.model = await loop.run_in_executor(None, ModelManager.get_model)

        if not self.codex or len(self.codex.strip()) < 100:
            logger.error(f"❌ Текст для {self.document_name} слишком короткий или пуст.")
            return False

        await self.create_embeddings_if_not_exists()
        return True

    def get_articles_chunks(self):
        if not self.codex: return []

        # 🔥 ИСПРАВЛЕНИЕ REGEX:
        # 1. (?i) - игнор регистра
        # 2. \s+ - обязательный пробел после слова Статья
        # 3. \d+ - номер
        # 4. \s* - (ВАЖНО) возможные пробелы или перенос строки перед точкой
        # 5. \.? - необязательная точка
        split_pattern = r'(?i)((?:Статья|ГЛАВА)\s+\d+\s*\.?|РАЗДЕЛ\s+[IVX]+)'

        raw_chunks = re.split(split_pattern, self.codex)

        chunks = []
        current_header = self.document_name

        # Если сплит не сработал (мало частей), берем весь текст
        if len(raw_chunks) < 2: raw_chunks = [self.codex]

        for i in range(len(raw_chunks)):
            segment = raw_chunks[i].strip()
            if not segment: continue

            # Проверяем, является ли сегмент заголовком (по тому же паттерну)
            if re.fullmatch(split_pattern, segment):
                current_header = segment
                # Нормализуем заголовок (убираем лишние переносы, например "Статья 4\n." -> "Статья 4.")
                current_header = re.sub(r'\s+', ' ', current_header).strip()
            else:
                full_text = f"{current_header}\n{segment}"
                if len(full_text) > 3000: full_text = full_text[:3000] + "..."

                chunks.append({
                    'text': full_text,
                    'article_source': self.document_name,
                    'article_title': current_header,
                    'paragraph_index': len(chunks)
                })

        logger.info(f"📄 Разбив текст {self.document_name}: получено {len(chunks)} чанков")
        return chunks

    async def create_embeddings_if_not_exists(self):
        try:
            loop = asyncio.get_running_loop()
            exists = await loop.run_in_executor(None, lambda: self.client.collection_exists(self.collection_name))

            if not exists:
                logger.info(f"🔧 Создаю коллекцию Qdrant: {self.collection_name}")
                await loop.run_in_executor(
                    None,
                    lambda: self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
                    )
                )
                await self.create_embeddings()
            else:
                count_result = await loop.run_in_executor(None, lambda: self.client.count(self.collection_name))
                if count_result.count == 0:
                    await self.create_embeddings()
        except Exception as e:
            logger.error(f"❌ Ошибка Qdrant Init: {e}")

    async def create_embeddings(self):
        try:
            chunks = self.get_articles_chunks()
            if not chunks:
                return

            texts = [f"passage: {c['text']}" for c in chunks]
            logger.info(f"⏳ Генерация векторов для {self.document_name} ({len(texts)} шт)...")

            loop = asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: self.model.encode(texts, normalize_embeddings=True)
            )

            points = [
                PointStruct(id=i, vector=vector.tolist(), payload=chunk)
                for i, (chunk, vector) in enumerate(zip(chunks, embeddings))
            ]

            await loop.run_in_executor(
                None,
                lambda: self.client.upsert(collection_name=self.collection_name, points=points)
            )
            logger.info(f"✅ Векторы загружены в {self.collection_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка создания эмбеддингов: {e}")

    async def search_relevant_chunks_async(self, question, limit=4):
        loop = asyncio.get_running_loop()

        def _encode_and_search():
            query_vector = self.model.encode(f"query: {question}", normalize_embeddings=True)
            return self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit
            )

        try:
            result = await loop.run_in_executor(None, _encode_and_search)
            context_parts = [f"--- {hit.payload.get('article_title', 'Отрывок')} ---\n{hit.payload.get('text', '')}" for
                             hit in result.points]
            return "\n\n".join(context_parts)
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            return ""

    async def answer_question(self, question):
        try:
            if not self.model:
                await self.initialize()

            context = await self.search_relevant_chunks_async(question)
            if not context:
                return "❌ Не удалось найти релевантную информацию в документе."

            system_prompt = (
                f"Ты юрист-педагог для детей по документу: {self.document_name}. "
                "Отвечай ТОЛЬКО на РУССКОМ языке, кратко, понятно для детей, упрощая некоторые подробности. Оптимальная длина ответа 150-300 символов"
                "Не используй латиницу"
                "Модешь ссылаться на номера статей или глав, если они есть в контексте. "
                "Не используй Markdown форматирование (жирный, курсив), пиши обычным текстом. Ответ должен быть корректен для отправки в чате Telegram"
            )
            user_content = f"Контекст:\n{context}\n\nВопрос пользователя: {question}"

            chat_completion = await self.groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                model=self.llm_model,
                temperature=0.3,
            )
            return chat_completion.choices[0].message.content

        except Exception as e:
            logger.error(f"Ошибка LLM (Groq): {e}")
            return "Произошла ошибка при генерации ответа."