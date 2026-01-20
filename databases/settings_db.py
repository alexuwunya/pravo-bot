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
                    voice_answers BOOLEAN DEFAULT 0,
                    voice_input BOOLEAN DEFAULT 0
                )
            ''')

            try:
                cursor.execute('ALTER TABLE user_settings ADD COLUMN voice_input BOOLEAN DEFAULT 0')
            except sqlite3.OperationalError:
                pass

            conn.commit()

    def set_voice_setting(self, user_id: int, enabled: bool):
        self._update_setting(user_id, 'voice_answers', enabled)

    def set_voice_input_setting(self, user_id: int, enabled: bool):
        self._update_setting(user_id, 'voice_input', enabled)

    def _update_setting(self, user_id: int, column: str, value: bool):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM user_settings WHERE user_id = ?', (user_id,))
            exists = cursor.fetchone()

            val = 1 if value else 0

            if exists:
                cursor.execute(f'UPDATE user_settings SET {column} = ? WHERE user_id = ?', (val, user_id))
            else:
                if column == 'voice_answers':
                    cursor.execute('INSERT INTO user_settings (user_id, voice_answers, voice_input) VALUES (?, ?, 0)',
                                   (user_id, val))
                else:
                    cursor.execute('INSERT INTO user_settings (user_id, voice_answers, voice_input) VALUES (?, 0, ?)',
                                   (user_id, val))
            conn.commit()

    def get_voice_setting(self, user_id: int) -> bool:
        return self._get_setting(user_id, 'voice_answers')

    def get_voice_input_setting(self, user_id: int) -> bool:
        return self._get_setting(user_id, 'voice_input')

    def _get_setting(self, user_id: int, column: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f'SELECT {column} FROM user_settings WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                return bool(result[0]) if result else False
            except Exception:
                return False

settings_db = SettingsDatabase()