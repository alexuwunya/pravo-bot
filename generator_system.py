import os
import json
import requests
import time
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
if not OPENROUTER_API_KEY:
    logger.critical("OPENROUTER_API_KEY не найден в переменных окружения!")
    exit(1)

YOUR_SITE_URL = "https://your-bot-url.com"
YOUR_SITE_NAME = "PravoBot"

MODEL = "meta-llama/llama-3.2-3b-instruct:free"

OUTPUT_FILE = "questions.json"
QUESTIONS_PER_BATCH = 5
TARGET_PER_TYPE = 50

TOPICS = [
    "Правила дорожного движения (велосипеды, самокаты, переходы)",
    "Права ребенка (Конвенция, Закон РБ о правах ребенка)",
    "Семья и обязанности родителей/детей",
    "Административная ответственность (мелкое хулиганство, шум, мусор)",
    "Финансовая грамотность (карманные деньги, покупки)",
    "Безопасность в интернете и кибербуллинг",
    "Государственные символы Республики Беларусь",
    "Школа и поведение на уроках"
]

TYPES = {
    "single": "Одиночный выбор (4 варианта, 1 верный)",
    "multiple": "Множественный выбор (4-5 вариантов, несколько верных)",
    "matching": "Соотнесение (4 пары: термин - определение)",
    "sequence": "Восстановление последовательности (5 шагов)",
    "fill-blanks": "Заполнение пропусков (текст с html-тегами)",
    "find-error": "Поиск ошибки (список утверждений, одно неверное)"
}

TEMPLATES = {
    "single": """{
    "type": "single",
    "question": "Текст вопроса?",
    "options": ["Вариант А", "Вариант Б", "Вариант В", "Вариант Г"],
    "correct": 0  // Индекс правильного ответа (0-3)
}""",
    "multiple": """{
    "type": "multiple",
    "question": "Текст вопроса?",
    "options": ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4"],
    "correct": [0, 2] // Список индексов правильных ответов
}""",
    "matching": """{
    "type": "matching",
    "question": "Соедини...",
    "leftItems": ["Термин 1", "Термин 2", "Термин 3", "Термин 4"],
    "rightItems": ["Опр 1", "Опр 2", "Опр 3", "Опр 4"],
    "correctPairs": {
        "Термин 1": "Опр 1",
        "Термин 2": "Опр 2",
        "Термин 3": "Опр 3",
        "Термин 4": "Опр 4"
    }
}""",
    "sequence": """{
    "type": "sequence",
    "question": "Расставь порядок...",
    "steps": ["Шаг 1", "Шаг 2", "Шаг 3", "Шаг 4", "Шаг 5"],
    "correctOrder": [0, 1, 2, 3, 4] // Всегда индексы от 0 до 4 в правильном логическом порядке
}""",
    "fill-blanks": """{
    "type": "fill-blanks",
    "question": "Заполни пропуски...",
    "code": "Текст до <span class=\\"blank\\" data-id=\\"1\\">______</span> текст после <span class=\\"blank\\" data-id=\\"2\\">______</span>.",
    "blanks": {
        "1": ["правильный1", "неверный1", "неверный2"],
        "2": ["правильный2", "неверный1", "неверный2"]
    },
    "correct": ["правильный1", "правильный2"]
}""",
    "find-error": """{
    "type": "find-error",
    "question": "Найди, кто нарушает закон:",
    "code": [
        "1. Утверждение правильное.",
        "2. Утверждение правильное.",
        "3. Утверждение с нарушением закона.",
        "4. Утверждение правильное."
    ],
    "errorLine": 3 // Номер строки с ошибкой (начиная с 1, как в визуальном отображении игры)
}"""
}


def clean_json_response(text: str) -> str:
    """Убирает маркдаун ```json ... ``` если модель его добавила"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def generate_batch(q_type, topic, count):
    prompt = f"""
    Ты — юрист-педагог для детей 8-14 лет в Республике Беларусь.
    Твоя задача: сгенерировать {count} вопросов для викторины в формате JSON.

    Тема вопросов: {topic}
    Тип вопросов: {TYPES[q_type]}

    СТРОГИЕ ПРАВИЛА:
    1. Язык: Русский.
    2. Контекст: Законы и реалии Беларуси (ПДД РБ, КоАП РБ, Конституция РБ).
    3. Стиль: Простой, детский, без канцеляризмов.
    4. ФОРМАТ: Верни ТОЛЬКО массив JSON объектов [{TEMPLATES[q_type]}, ...]. Никакого вводного текста.
    5. Важно для типа 'fill-blanks': в поле 'code' используй HTML теги <span class="blank" data-id="N">______</span>. Будь аккуратен с кавычками внутри JSON.

    Пример JSON структуры (верни массив таких объектов):
    {TEMPLATES[q_type]}
    """

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": YOUR_SITE_URL,
        "X-Title": YOUR_SITE_NAME,
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Ты полезный ассистент, который генерирует валидный JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content']
        cleaned_content = clean_json_response(content)
        return json.loads(cleaned_content)
    except Exception as e:
        print(f"Ошибка при генерации ({q_type}): {e}")
        # Если ошибка парсинга, выведем сырой ответ для отладки
        if 'content' in locals():
            print(f"Сырой ответ: {content[:100]}...")
        return []


def main():
    all_questions = []

    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            try:
                all_questions = json.load(f)
                print(f"Загружено существующих вопросов: {len(all_questions)}")
            except:
                print("Файл поврежден или пуст, начинаем с нуля.")

    for q_type in TYPES.keys():
        current_type_count = sum(1 for q in all_questions if q.get('type') == q_type)
        print(f"\n--- Обработка типа: {q_type} (Уже есть: {current_type_count}) ---")

        while current_type_count < TARGET_PER_TYPE:
            # Выбираем тему циклично
            topic = TOPICS[current_type_count % len(TOPICS)]
            needed = min(QUESTIONS_PER_BATCH, TARGET_PER_TYPE - current_type_count)

            print(f"Генерируем {needed} вопросов по теме: '{topic}'...")

            new_questions = generate_batch(q_type, topic, needed)

            if new_questions:
                all_questions.extend(new_questions)
                current_type_count += len(new_questions)

                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_questions, f, ensure_ascii=False, indent=2)

                print(f"Успешно! Всего {q_type}: {current_type_count}/{TARGET_PER_TYPE}")
            else:
                print("Неудачная попытка, ждем 5 сек...")

            time.sleep(2)

    print(f"\nГотово! Все вопросы сохранены в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()