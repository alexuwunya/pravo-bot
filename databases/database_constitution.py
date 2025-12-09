import sqlite3
import re
import logging

logger = logging.getLogger(__name__)


class ConstitutionDatabase:
    def __init__(self, db_path="constitution.db"):
        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS constitution_text (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_text TEXT,
                    url TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sentence TEXT,
                    sentence_index INTEGER,
                    keywords TEXT
                )
            ''')
            conn.commit()

    def is_constitution_loaded(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM constitution_text')
                text_exists = cursor.fetchone()[0] > 0
                return text_exists
        except Exception as e:
            logger.error(f"DB Error: {e}")
            return False

    def save_constitution(self, full_text, url):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM constitution_text')
            cursor.execute('DELETE FROM search_index')

            cursor.execute('INSERT INTO constitution_text (full_text, url) VALUES (?, ?)', (full_text, url))

            sentences = re.split(r'(?<=[.!?])\s+', full_text)  # Более умная разбивка

            batch_data = []
            for i, sentence in enumerate(sentences):
                s_clean = sentence.strip()
                if s_clean:
                    words = [w.lower() for w in re.findall(r'\b\w{4,}\b', s_clean)]
                    keywords = ' '.join(words)
                    batch_data.append((s_clean, i, keywords))

            if batch_data:
                cursor.executemany('INSERT INTO search_index (sentence, sentence_index, keywords) VALUES (?, ?, ?)',
                                   batch_data)

            conn.commit()
            logger.info(f"Конституция сохранена. Индексировано {len(batch_data)} предложений.")

    def get_constitution_text(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT full_text FROM constitution_text LIMIT 1')
            res = cursor.fetchone()
            return res[0] if res else None

    def clear_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM constitution_text')
            cursor.execute('DELETE FROM search_index')
            conn.commit()


constitution_db = ConstitutionDatabase()