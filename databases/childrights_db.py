import logging
import re
from bs4 import BeautifulSoup
from databases.base_legal_db import BaseLegalDatabase

logger = logging.getLogger(__name__)


class ChildRightsDatabase(BaseLegalDatabase):
    def __init__(self):
        super().__init__("child_rights.db", "child_rights")

    async def update_from_source(self) -> bool:
        url = "https://etalonline.by/document/?regnum=v19302570"
        logger.info(f"🔄 Обновление Прав Ребенка из {url}")

        html = await self._fetch_html(url)
        if not html: return False

        try:
            soup = BeautifulSoup(html, 'html.parser')
            container = soup.find('div', {'class': 'text'}) or soup.find('div', {'class': 'Section1'})

            if container:
                for tag in container(["script", "style"]):
                    tag.decompose()
                full_text = container.get_text(separator='\n', strip=True)
            else:
                full_text = soup.get_text(separator='\n', strip=True)


            start_markers = ["ЗАКОН РЕСПУБЛИКИ БЕЛАРУСЬ", "О правах ребенка", "Настоящий Закон основывается"]
            end_marker = "Президент Республики Беларусь"

            start_index = -1
            for marker in start_markers:
                idx = full_text.find(marker)
                if idx != -1:
                    start_index = idx
                    break

            end_index = full_text.rfind(end_marker)

            if start_index != -1 and end_index != -1:
                full_text = full_text[start_index: end_index + 100]
                final_cut = full_text.find("А.Лукашенко")
                if final_cut != -1:
                    full_text = full_text[:final_cut + 11]

            full_text = re.sub(r'\n{3,}', '\n\n', full_text)

            if "ребен" not in full_text.lower():
                return False

            self.save_text(full_text, url)
            logger.info(f"✅ Права ребенка обновлены. Длина: {len(full_text)}")
            return True
        except Exception as e:
            logger.error(f"Parse Error: {e}")
            return False


child_rights_db = ChildRightsDatabase()