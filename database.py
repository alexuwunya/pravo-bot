import sqlite3
import re

class ConstitutionDatabase:
    def __init__(self, db_path="constitution.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица для хранения текста Конституции
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
        conn.close()
    
    def is_constitution_loaded(self):
        """Проверяет, загружена ли Конституция в базу данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM constitution_text')
        count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM search_index')
        index_count = cursor.fetchone()[0]
        
        conn.close()
        
        return count > 0 and index_count > 0
    
    def save_constitution(self, full_text, url):

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM constitution_text')
        cursor.execute('DELETE FROM search_index')
        
        cursor.execute('''
            INSERT INTO constitution_text (full_text, url)
            VALUES (?, ?)
        ''', (full_text, url))
        
        constitution_id = cursor.lastrowid
        
        # Индексируем предложения
        sentences = re.split(r'[.!?]+', full_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        for i, sentence in enumerate(sentences):
            words = re.findall(r'\b\w{4,}\b', sentence.lower())
            keywords = ' '.join(words)
            
            cursor.execute('''
                INSERT INTO search_index (sentence, sentence_index, keywords)
                VALUES (?, ?, ?)
            ''', (sentence, i, keywords))
        
        conn.commit()
        conn.close()
        
        return constitution_id
    
    def search_sentences(self, keyword):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT full_text FROM constitution_text LIMIT 1')
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return []
        
        full_text = result[0]
        
        cursor.execute('''
            SELECT sentence, sentence_index 
            FROM search_index 
            WHERE sentence LIKE ? OR keywords LIKE ?
            ORDER BY sentence_index
        ''', (f'%{keyword}%', f'%{keyword}%'))
        
        found_sentences = cursor.fetchall()
        conn.close()
        
        all_sentences = re.split(r'[.!?]+', full_text)
        all_sentences = [s.strip() for s in all_sentences if s.strip()]
        
        sentences_data = []
        for sentence, sentence_index in found_sentences:
            sentences_data.append({
                'index': sentence_index,
                'sentence': sentence,
                'context_before': all_sentences[max(0, sentence_index-2):sentence_index] if sentence_index > 0 else [],
                'context_after': all_sentences[sentence_index+1:min(len(all_sentences), sentence_index+3)] if sentence_index < len(all_sentences)-1 else []
            })
        
        return sentences_data
    
    def get_constitution_info(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) as sentence_count, 
                   last_updated 
            FROM constitution_text ct
            JOIN search_index si ON 1=1
            GROUP BY ct.id
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'sentence_count': result[0],
                'last_updated': result[1]
            }
        return None

    def get_constitution_text(self):
        """Получает полный текст Конституции из БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT full_text FROM constitution_text LIMIT 1')
        result = cursor.fetchone()

        conn.close()

        if result:
            return result[0]
        return None

constitution_db = ConstitutionDatabase()