from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import requests

#Рабочая раг система, отвечает на запросы пользователя по конституции
class RAGSystem:
    def __init__(self, paragraph):
        print('init')
        self.model = SentenceTransformer("intfloat/multilingual-e5-large")
        self.client = QdrantClient(path="\\qdrant_client")
        self.api_key = "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"
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.llm_model = "qwen/qwen3-30b-a3b:free"
        self.codex = paragraph
        self.create_embeddings_if_not_exists()

    def get_articles_chunks(self):
        print('gettin chunks')
        codex = self.codex
        articles = codex.split("Статья")
        chunks = []
        for v, article in enumerate(articles):
            if v == 0:
                title = "Преамбула"
            else:
                first_space = articles[v].find(' ')
                second_space = articles[v].find(' ', first_space + 1)
                title = f"Статья {articles[v][first_space:second_space]}"
            paragraphs = article.split('\n\n')
            for j, paragraph in enumerate(paragraphs):
                if paragraph.strip():
                    chunks.append({
                        'text': paragraph.strip(),
                        'article_source': 'Конституция',
                        'article_title': title,
                        'paragraph_index': j
                    })
        return chunks

    def create_embeddings_if_not_exists(self):
        print('creatin embeddings')
        if not self.client.collection_exists("constitution_articles"):
            self.client.create_collection(
                collection_name="constitution_articles",
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            self.create_embeddings()

    def create_embeddings(self):
        paragraphs = self.get_articles_chunks()
        articles = [f"passage: {paragraph['text']}" for paragraph in paragraphs]

        embeddings = self.model.encode(articles, normalize_embeddings=True)
        print(f"Создано {embeddings.shape[0]} эмбеддингов")

        points = []
        for i, (paragraph, vector) in enumerate(zip(paragraphs, embeddings)):
            points.append({
                "id": i,
                "vector": vector.tolist(),
                "payload": {
                    "text": paragraph['text'],
                    "article_title": paragraph['article_title'],
                    "article_source": paragraph['article_source'],
                    "paragraph_index": paragraph['paragraph_index']
                }
            })

        self.client.upsert(
            collection_name="constitution_articles",
            points=points
        )

        print(f"Сохранено {len(points)} точек в векторную БД")

    def search_relevant_chunks(self, question, limit=5):
        print('searchin')
        query_text = f"query: {question}"
        query_vector = self.model.encode(query_text, normalize_embeddings=True)

        search_result = self.client.query_points(
            collection_name="constitution_articles",
            query=query_vector,
            limit=limit
        )
        hits = search_result.points

        context_parts = []
        for i, hit in enumerate(hits, 1):
            payload = hit.payload
            context_parts.append(f"[Документ {i}] {payload['article_title']}: {payload['text']}")
        return "\n\n".join(context_parts)

    def ask_llm(self, question, context):
        print('askin')
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://t.me/detpravo_bot",
            "X-Title": "RAG Assistant"
        }

        system_prompt = """Ты - юридический ассистент, специализирующийся на Конституции Республики Беларусь. 
Используй ТОЛЬКО предоставленные фрагменты конституции для ответа на вопрос. 

ПРАВИЛА ОТВЕТА:
1. Отвечай ТОЛЬКО на основе предоставленного контекста
2. Если в контексте нет информации для ответа, скажи: "В предоставленных фрагментах Конституции нет информации для ответа на этот вопрос"
3. Не упоминай, что информация взята из фрагментов или что какие-то части отсутствуют
4. Отвечай четко, структурированно и профессионально
5. Указывай конкретные статьи Конституции, на которые ты ссылаешься
6. Отвечай на русском языке

Важно: Не добавляй никаких комментариев о том, что чего-то нет в контексте или о ограничениях предоставленных фрагментов.
Если какая-либо информация является излишнией, нерелевантной, то не упоминай её в ответе"""

        user_content = f"""Контекст из Конституции Республики Беларусь:
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
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)

            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"Ошибка при запросе к LLM: {response.status_code}\n{response.text}"
        except requests.exceptions.Timeout:
            return "Превышено время ожидания ответа от сервиса."
        except Exception as e:
            return f"Ошибка при обращении к сервису: {str(e)}"

    def answer_question(self, question):
        print('answerin')
        context = self.search_relevant_chunks(question)
        print('askin llm')
        answer = self.ask_llm(question, context)
        print('suda')
        return answer

#Тестирование
if __name__ == "__main__":
    with open("C:\\Users\\ililio\\Desktop\\constitution.txt", "r", encoding="utf-8") as f:
        text = f.read()
    print('lol')
    rag_system = RAGSystem(text)
    while True:
        ans = rag_system.answer_question(input())
        print(ans)