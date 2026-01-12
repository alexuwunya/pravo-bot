import sqlite3
import logging

logger = logging.getLogger(__name__)

class SettingsDatabase:
    def __init__(self, db_path="settings.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    voice_answers BOOLEAN DEFAULT 0
                )
            ''')
            conn.commit()

    def set_voice_setting(self, user_id: int, enabled: bool):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_settings (user_id, voice_answers)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET voice_answers=excluded.voice_answers
            ''', (user_id, 1 if enabled else 0))
            conn.commit()

    def get_voice_setting(self, user_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT voice_answers FROM user_settings WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return bool(result[0]) if result else False

settings_db = SettingsDatabase()