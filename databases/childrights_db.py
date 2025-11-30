import sqlite3
import re
import requests
from bs4 import BeautifulSoup

class ChildRightsDatabase:
    def __init__(self, db_path="child_rights.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS child_rights_text (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_text TEXT,
                url TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS child_rights_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sentence TEXT,
                sentence_index INTEGER,
                keywords TEXT,
                article_number TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def is_law_loaded(self):
        """Проверяет, загружен ли закон в базу данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM child_rights_text')
        count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM child_rights_index')
        index_count = cursor.fetchone()[0]

        conn.close()

        return count > 0 and index_count > 0

    def parse_law_from_url(self, url="https://etalonline.by/document/?regnum=v19302570"):
        """Парсит закон с сайта etalonline.by"""
        try:
            response = requests.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            content_div = soup.find('div', {'id': 'userContent'})
            if not content_div:
                raise Exception("Не найден элемент с контентом закона")

            for element in content_div.find_all(['script', 'style', 'a']):
                element.decompose()

            full_text = content_div.get_text(separator='\n', strip=True)

            # Очищаем текст от лишних пробелов и переносов
            lines = [line.strip() for line in full_text.split('\n') if line.strip()]
            clean_text = '\n'.join(lines)

            return clean_text, url

        except Exception as e:
            print(f"Ошибка при парсинге закона: {e}")
            return None, None

    def save_law(self, full_text, url):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM child_rights_text')
        cursor.execute('DELETE FROM child_rights_index')

        cursor.execute('''
            INSERT INTO child_rights_text (full_text, url)
            VALUES (?, ?)
        ''', (full_text, url))

        law_id = cursor.lastrowid

        sentences = re.split(r'[.!?]+', full_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        conn.commit()
        conn.close()

        return law_id

    def get_law_text(self):
        """Получает полный текст закона из БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT full_text FROM child_rights_text LIMIT 1')
        result = cursor.fetchone()

        conn.close()

        if result:
            return result[0]
        return None

# Создаем глобальный экземпляр базы данных
child_rights_db = ChildRightsDatabase()

# Функция для загрузки и инициализации закона
def initialize_child_rights_law():
    if not child_rights_db.is_law_loaded():
        print("Загрузка закона 'О правах ребенка'...")
        text, url = child_rights_db.parse_law_from_url()
        if text:
            child_rights_db.save_law(text, url)
            print("Закон успешно загружен и сохранен в БД")
        else:
            print("Ошибка загрузки закона")
    else:
        print("Закон уже загружен в БД")