import os
import re
import logging
import json
import aiohttp
import asyncio
from sentence_transformers import SentenceTransformer
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_manager import qdrant_manager

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
    def __init__(self, paragraph, collection_name="constitution_articles", document_name='Конституция'):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ OPENROUTER_API_KEY не найден! RAG не будет работать корректно.")

        self.client = qdrant_manager.get_client()
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.llm_model = "google/gemma-3-27b-it:free"  # Обновил модель на более стабильную free версию, если доступна
        self.codex = paragraph
        self.document_name = document_name
        self.collection_name = collection_name

        self.model = ModelManager.get_model()

        logger.info(f"🔍 Init RAG для: {self.document_name}, Коллекция: {self.collection_name}")

        self._validate_input_text()
        self.create_embeddings_if_not_exists()

    def _validate_input_text(self):
        if not self.codex or len(self.codex.strip()) < 100:
            logger.error(f"Текст для {self.document_name} слишком короткий.")
            return

        if "О правах ребенка" in self.codex and "Конституция" in self.document_name:
            logger.warning("⚠️ Возможно перепутан текст документа (Конституция <> Права ребенка).")

    def get_articles_chunks(self):
        if not self.codex:
            return []

        chunks = []
        raw_chunks = re.split(r'(Статья \d+\.|ГЛАВА \d+)', self.codex)

        current_header = self.document_name

        for i in range(len(raw_chunks)):
            segment = raw_chunks[i].strip()
            if not segment:
                continue

            if re.match(r'(Статья \d+\.|ГЛАВА \d+)', segment):
                current_header = segment
            else:
                full_text = f"{current_header}\n{segment}"
                chunks.append({
                    'text': full_text,
                    'article_source': self.document_name,
                    'article_title': current_header,
                    'paragraph_index': i
                })

        logger.info(f"📄 Создано {len(chunks)} чанков для {self.document_name}")
        return chunks

    def create_embeddings_if_not_exists(self):
        try:
            if not self.client.collection_exists(self.collection_name):
                logger.info(f"🔧 Создаю коллекцию Qdrant: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
                )
                self.create_embeddings()
            else:
                count = self.client.count(self.collection_name).count
                if count == 0:
                    logger.info(f"⚠️ Коллекция {self.collection_name} пуста, пересоздаю эмбеддинги.")
                    self.create_embeddings()
        except Exception as e:
            logger.error(f"❌ Ошибка Qdrant: {e}")

    def create_embeddings(self):
        try:
            chunks = self.get_articles_chunks()
            if not chunks:
                return

            texts = [f"passage: {c['text']}" for c in chunks]

            logger.info("⏳ Генерация векторов...")
            embeddings = self.model.encode(texts, normalize_embeddings=True)

            points = []
            for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                points.append(PointStruct(
                    id=i,
                    vector=vector.tolist(),
                    payload=chunk
                ))

            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"✅ Загружено {len(points)} векторов в {self.collection_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка создания эмбеддингов: {e}")

    async def search_relevant_chunks_async(self, question, limit=4):
        loop = asyncio.get_running_loop()

        def _encode_and_search():
            query_vector = self.model.encode(f"query: {question}", normalize_embeddings=True)
            search_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit
            )
            return search_result

        try:
            result = await loop.run_in_executor(None, _encode_and_search)

            context_parts = []
            for hit in result.points:
                context_parts.append(
                    f"--- {hit.payload.get('article_title', 'Отрывок')} ---\n{hit.payload.get('text', '')}")

            return "\n\n".join(context_parts)
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            return ""

    async def answer_question(self, question):
        try:
            context = await self.search_relevant_chunks_async(question)
            if not context:
                return "❌ Не удалось найти информацию в документах."

            system_prompt = f"Ты юрист-консультант по документу: {self.document_name}. Отвечай кратко, по сути, придерживайся длины ответа в 100-200 символов, не исользуй специальные символы Markdown разметки ссылаяйся на статьи. Представь ответ, готовый к отображению в telegram"
            user_content = f"Контекст:\n{context}\n\nВопрос: {question}"

            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ]
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://telegram.bot",  # Требование OpenRouter
                }

                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content']
                    else:
                        err = await response.text()
                        logger.error(f"LLM Error {response.status}: {err}")
                        return "Ошибка при обращении к нейросети."

        except Exception as e:
            logger.error(f"Ошибка RAG: {e}")
            return "Произошла внутренняя ошибка системы."


class LegalRAGSystem(RAGSystem):
    def __init__(self, paragraph, document_name):
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '', document_name.lower().replace(' ', '_'))
        collection_name = f"legal_{safe_name}"
        super().__init__(paragraph, collection_name, document_name)