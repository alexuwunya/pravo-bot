import sqlite3
import logging
import aiohttp

logger = logging.getLogger(__name__)

class BaseLegalDatabase:
    def __init__(self, db_path: str, table_prefix: str):
        self.db_path = db_path
        self.table_name = f"{table_prefix}_text"
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute(f'''
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id INTEGER PRIMARY KEY,
                    full_text TEXT,
                    url TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

    def is_loaded(self) -> bool:
        """Проверяет, есть ли данные в базе"""
        try:
            with self._get_conn() as conn:
                res = conn.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()
                return res[0] > 0
        except:
            return False

    def save_text(self, text: str, url: str):
        with self._get_conn() as conn:
            conn.execute(f"DELETE FROM {self.table_name}")
            conn.execute(f"INSERT INTO {self.table_name} (full_text, url) VALUES (?, ?)", (text, url))
            conn.commit()

    def get_text(self) -> str:
        with self._get_conn() as conn:
            res = conn.execute(f"SELECT full_text FROM {self.table_name} LIMIT 1").fetchone()
            return res[0] if res else ""

    async def _fetch_html(self, url: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        # Используем read() и декодируем вручную для надежности с кириллицей
                        content = await resp.read()
                        return content.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Network error {url}: {e}")
        return ""

    async def update_from_source(self) -> bool:
        raise NotImplementedError