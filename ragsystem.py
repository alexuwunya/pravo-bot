from sentence_transformers import SentenceTransformer
from qdrant_client.models import VectorParams, Distance, PointStruct
import requests
from qdrant_manager import qdrant_manager
import re
import logging

logger = logging.getLogger(__name__)

class ModelManager:
    _instance = None
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            logger.info("🔧 Загружаю модель SentenceTransformer...")
            try:
                cls._model = SentenceTransformer("intfloat/multilingual-e5-large")
                logger.info("✅ Модель загружена")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки модели: {e}")
                raise
        return cls._model

class RAGSystem:
    def __init__(self, paragraph, collection_name="constitution_articles", document_name='Конституция'):
        try:
            self.model = ModelManager.get_model()
            self.client = qdrant_manager.get_client()
            self.api_key = "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"
            self.api_url = "https://openrouter.ai/api/v1/chat/completions"
            self.llm_model = "google/gemma-3-27b-it:free"
            self.codex = paragraph
            self.document_name = document_name
            self.collection_name = collection_name

            logger.info(f"🔍 Инициализация RAG системы для: {self.document_name}")
            logger.info(f"📝 Длина текста: {len(self.codex)} символов")
            logger.info(f"📚 Коллекция: {self.collection_name}")

            # Улучшенная валидация текста
            self._validate_input_text()
            self.create_embeddings_if_not_exists()

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации RAGSystem: {e}")
            raise

    def _validate_input_text(self):
        """Проверяет валидность входного текста"""
        if not self.codex or len(self.codex.strip()) < 100:
            raise ValueError("Текст документа слишком короткий или пустой")

        # Проверка на перекрестное загрязнение
        if "О правах ребенка" in self.codex and "Конституция" in self.document_name:
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: В текст Конституции попал закон о правах ребенка!")
            raise ValueError("Неверный текст документа")

    def get_articles_chunks(self):
        """Основной метод разбивки текста на чанки"""
        logger.info(f"🔧 Разбиваю текст {self.document_name} на чанки...")

        if not self.codex:
            logger.error("Текст для разбивки отсутствует")
            return []

        # Для Конституции используем специальный метод разбивки
        if self.document_name == 'Конституция Республики Беларусь':
            return self._get_constitution_chunks()
        else:
            # Для других документов используем общий метод
            return self._get_general_chunks()

    def _get_constitution_chunks(self):
        """Специальный метод разбивки текста Конституции на чанки"""
        try:
            chunks = []
            current_title = "Преамбула"

            # Разбиваем на разделы с сохранением разделителей
            sections = re.split(r'(РАЗДЕЛ [IVXLCDM]+|ГЛАВА \d+)', self.codex)

            for i, section in enumerate(sections):
                if i == 0 and section.strip():
                    # Преамбула
                    chunks.append(self._create_chunk(section.strip(), "Преамбула", 0))
                elif i % 2 == 1:
                    # Название раздела/главы
                    current_title = section.strip()
                elif section.strip():
                    # Текст раздела
                    self._process_section_text(section.strip(), current_title, chunks)

            # Резервный метод если основной не сработал
            if len(chunks) <= 1:
                logger.warning("🔧 Основной метод разбивки не сработал, использую резервный...")
                chunks = self._get_constitution_chunks_fallback()

            logger.info(f"📄 Создано {len(chunks)} чанков для Конституции")
            return chunks

        except Exception as e:
            logger.error(f"Ошибка при разбивке Конституции: {e}")
            return self._get_fallback_chunk()

    def _process_section_text(self, section_text, current_title, chunks):
        """Обрабатывает текст раздела и разбивает на статьи"""
        articles = re.split(r'Статья \d+', section_text)
        for j, article in enumerate(articles):
            if article.strip():
                if j == 0 and "Статья" not in section_text[:100]:
                    article_title = current_title
                else:
                    article_title = f"{current_title}, Статья {j}"

                chunks.append(self._create_chunk(article.strip(), article_title, j))

    def _get_constitution_chunks_fallback(self):
        """Резервный метод разбивки Конституции"""
        try:
            chunks = []
            parts = re.split(r'(Статья \d+)', self.codex)

            for i in range(0, len(parts)):
                if i == 0 and parts[i].strip():
                    chunks.append(self._create_chunk(parts[i].strip(), "Преамбула", 0))
                elif i % 2 == 1 and i + 1 < len(parts):
                    article_title = parts[i].strip()
                    article_text = parts[i + 1].strip()
                    if article_text:
                        chunks.append(self._create_chunk(article_text, article_title, len(chunks)))
            return chunks
        except Exception as e:
            logger.error(f"Ошибка в резервном методе разбивки: {e}")
            return self._get_fallback_chunk()

    def _get_general_chunks(self):
        """Общий метод разбивки текста на чанки для любых документов"""
        try:
            chunks = []
            lines = self.codex.split('\n')
            current_title = f"Раздел {self.document_name}"
            current_text = ""

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Если находим начало статьи или раздела
                if any(line.startswith(keyword) for keyword in ['Статья', 'Глава', 'РАЗДЕЛ']):
                    if current_text:
                        chunks.append(self._create_chunk(current_text.strip(), current_title, 0))
                    current_title = line
                    current_text = ""
                else:
                    current_text += line + " "

            # Добавляем последний раздел
            if current_text:
                chunks.append(self._create_chunk(current_text.strip(), current_title, 0))

            # Если не удалось разбить на разделы, создаем один большой чанк
            if not chunks:
                chunks = [self._get_fallback_chunk()]

            logger.info(f"📄 Создано {len(chunks)} чанков для {self.document_name}")
            return chunks

        except Exception as e:
            logger.error(f"Ошибка при общей разбивке текста: {e}")
            return [self._get_fallback_chunk()]

    def _create_chunk(self, text, title, index):
        """Создает структурированный чанк"""
        return {
            'text': text,
            'article_source': self.document_name,
            'article_title': title,
            'paragraph_index': index
        }

    def _get_fallback_chunk(self):
        """Создает резервный чанк при ошибках"""
        return self._create_chunk(
            self.codex[:2000] if self.codex else "Текст отсутствует",
            self.document_name,
            0
        )

    def create_embeddings_if_not_exists(self):
        """Создает коллекцию и эмбеддинги если они не существуют"""
        try:
            logger.info(f"🔍 Проверяю коллекцию {self.collection_name}...")
            if not self.client.collection_exists(self.collection_name):
                logger.info(f"🔧 Создаю коллекцию {self.collection_name}...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
                )
                self.create_embeddings()
                logger.info(f"✅ Коллекция {self.collection_name} создана и эмбеддинги сгенерированы")
            else:
                logger.info(f"✅ Коллекция {self.collection_name} уже существует")
        except Exception as e:
            logger.error(f"❌ Ошибка при создании коллекции {self.collection_name}: {e}")
            raise

    def create_embeddings(self):
        """Создает эмбеддинги для всех чанков"""
        try:
            paragraphs = self.get_articles_chunks()
            if not paragraphs:
                logger.error("❌ Нет параграфов для создания эмбеддингов")
                return

            # Логируем информацию о первом чанке для отладки
            if paragraphs:
                first_chunk_preview = paragraphs[0]['text'][:100] + "..." if len(paragraphs[0]['text']) > 100 else paragraphs[0]['text']
                logger.info(f"🔍 Первый чанк: {first_chunk_preview}")

            articles = [f"passage: {paragraph['text']}" for paragraph in paragraphs]

            logger.info(f"🔧 Кодирую {len(articles)} параграфов для {self.document_name}...")
            embeddings = self.model.encode(articles, normalize_embeddings=True)
            logger.info(f"✅ Создано {embeddings.shape[0]} эмбеддингов")

            points = []
            for i, (paragraph, vector) in enumerate(zip(paragraphs, embeddings)):
                points.append(PointStruct(
                    id=i,
                    vector=vector.tolist(),
                    payload={
                        "text": paragraph['text'],
                        "article_title": paragraph['article_title'],
                        "article_source": paragraph['article_source'],
                        "paragraph_index": paragraph['paragraph_index']
                    }
                ))

            logger.info(f"🔧 Сохраняю {len(points)} точек в Qdrant...")
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"✅ Сохранено {len(points)} точек в коллекцию {self.collection_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка при создании эмбеддингов для {self.document_name}: {e}")
            raise

    def search_relevant_chunks(self, question, limit=5):
        """Ищет релевантные чанки для вопроса"""
        try:
            logger.info(f"🔍 Ищу в коллекции {self.collection_name}: {question}")
            query_text = f"query: {question}"
            query_vector = self.model.encode(query_text, normalize_embeddings=True)

            search_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit
            )
            hits = search_result.points

            context_parts = []
            for i, hit in enumerate(hits, 1):
                payload = hit.payload
                context_parts.append(f"[Документ {i}] {payload['article_title']}: {payload['text']}")

            logger.info(f"✅ Найдено {len(context_parts)} релевантных фрагментов")
            return "\n\n".join(context_parts)

        except Exception as e:
            logger.error(f"❌ Ошибка при поиске в {self.collection_name}: {e}")
            return ""

    def ask_llm(self, question, context):
        """Отправляет запрос к LLM"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://t.me/detpravo_bot",
            "X-Title": "RAG Assistant"
        }

        system_prompt = f"""Ты — юридический ассистент по {self.document_name}. Твоя задача — давать точные и структурированные ответы на основе {self.document_name}.

        КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
        1. **Источник информации:** Для ответа используй только текст {self.document_name}, предоставленный в контексте запроса.
        2. **Если ответа нет:** Если в предоставленном тексте {self.document_name} нет информации даже близкой к теме вопроса, строго скажи: «В {self.document_name} не найдено информации для ответа на этот вопрос».
        3. **Недопустимые формулировки:** Запрещено упоминать в ответе «фрагменты», «контекст», «предоставленные данные» или любые другие слова, раскрывающие механизм твоей работы.
        4. **Чистота ответа:** Ответ должен быть обычным текстом. ЗАПРЕЩЕНО использовать Markdown-разметку.

        ПРАВИЛА ФОРМАТИРОВАНИЯ ОТВЕТА:
        - Отвечай четко, структурированно и профессионально на русском языке.
        - В самом начале ответа кратко сформулируй суть ответа.
        - Обязательно указывай номера конкретных статей документа, на которые ты опираешься.
        - Излагай информацию тезисно, используя абзацы и списки.
        """

        user_content = f"""Контекст из {self.document_name}:
{context}

Вопрос: {question}

На основе приведенного контекста дай четкий ответ:"""

        data = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "max_tokens": 1024
        }

        try:
            logger.info(f"🔍 Отправляю запрос к LLM с вопросом: {question}")
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()

            result = response.json()
            answer = result['choices'][0]['message']['content']
            logger.info(f"✅ Получен ответ от LLM, длина: {len(answer)} символов")
            return answer

        except requests.exceptions.Timeout:
            logger.error("❌ Превышено время ожидания ответа от LLM")
            return "Превышено время ожидания ответа от сервиса."
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сети при запросе к LLM: {e}")
            return f"Ошибка подключения к сервису: {str(e)}"
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при запросе к LLM: {e}")
            return f"Ошибка при обращении к сервису: {str(e)}"

    def answer_question(self, question):
        """Основной метод для ответа на вопрос"""
        try:
            logger.info(f"🔍 Начало обработки вопроса: {question}")
            context = self.search_relevant_chunks(question)
            if not context:
                logger.warning("❌ Не удалось найти релевантный контекст")
                return f"❌ Не удалось найти релевантную информацию в {self.document_name}."

            logger.info(f"✅ Контекст найден, длина: {len(context)} символов")
            answer = self.ask_llm(question, context)
            return answer

        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке вопроса: {e}")
            return f"❌ Произошла ошибка при обработке вашего запроса. Попробуйте позже."

class LegalRAGSystem(RAGSystem):
    def __init__(self, paragraph, document_name):
        collection_name = f"legal_document_{document_name.lower().replace(' ', '_')}"
        super().__init__(paragraph, collection_name, document_name)