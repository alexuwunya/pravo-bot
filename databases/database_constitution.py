import logging
import re
from bs4 import BeautifulSoup
from databases.base_legal_db import BaseLegalDatabase

logger = logging.getLogger(__name__)


class ConstitutionDatabase(BaseLegalDatabase):
    def __init__(self):
        super().__init__("constitution.db", "constitution")

    async def update_from_source(self) -> bool:
        url = "https://etalonline.by/document/?regnum=v19402875&q_id=2524604"
        logger.info(f"🔄 Обновление Конституции из {url}")

        html = await self._fetch_html(url)
        if not html: return False

        try:
            soup = BeautifulSoup(html, 'html.parser')

            container = soup.find('div', {'class': 'text'}) or soup.find('div', {'class': 'Section1'})

            if container:
                for tag in container(["script", "style", "meta", "link"]):
                    tag.decompose()
                full_text = container.get_text(separator='\n', strip=True)
            else:
                full_text = soup.get_text(separator='\n', strip=True)

            start_marker = "Мы, народ Республики Беларусь"
            end_marker = "Президент Республики Беларусь"

            start_index = full_text.find(start_marker)
            end_index = full_text.rfind(end_marker)

            if start_index != -1 and end_index != -1:
                full_text = full_text[start_index: end_index + 100]

                final_cut = full_text.find("А.Лукашенко")
                if final_cut != -1:
                    full_text = full_text[:final_cut + 11]  # +11 символов длины "А.Лукашенко"

            full_text = re.sub(r'\n{3,}', '\n\n', full_text)

            if "Конституция" not in full_text and "народ" not in full_text:
                logger.error("❌ Текст Конституции не прошел валидацию")
                return False

            self.save_text(full_text, url)
            logger.info(f"✅ Конституция обновлена. Длина чистого текста: {len(full_text)}")
            return True
        except Exception as e:
            logger.error(f"Parse Error: {e}")
            return False


constitution_db = ConstitutionDatabase()