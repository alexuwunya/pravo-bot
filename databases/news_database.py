import sqlite3
import aiohttp
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class NewsDatabase:
    def __init__(self, db_path="news.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица для хранения новостей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                date TEXT,
                category TEXT,
                content_text TEXT,
                full_content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица для поискового индекса
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news_search_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                keywords TEXT,
                FOREIGN KEY (article_id) REFERENCES news_articles (id)
            )
        ''')
        
        # Таблица для отслеживания обновлений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS update_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                articles_processed INTEGER,
                new_articles INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def needs_update(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT last_update FROM update_log ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return True
        
        last_update = datetime.fromisoformat(result[0])
        return datetime.now() - last_update > timedelta(hours=1)
    
    async def parse_article_content(self, url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        content_div = soup.find('div', class_='article-content')
                        if content_div:
                            full_content = content_div.get_text(separator='\n', strip=True)
                            
                            cleaned_content = re.sub(r'\s+', ' ', full_content).strip()
             
                            preview_content = cleaned_content[:300] + "..." if len(cleaned_content) > 300 else cleaned_content
                            
                            return {
                                'full_content': cleaned_content,
                                'preview_content': preview_content
                            }
        except Exception as e:
            logger.error(f"Ошибка парсинга контента статьи {url}: {str(e)}")
        
        return None
    
    def save_article(self, article_data):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT id FROM news_articles WHERE url = ?', (article_data['url'],))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute('''
                    UPDATE news_articles 
                    SET title = ?, date = ?, category = ?, content_text = ?, full_content = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE url = ?
                ''', (
                    article_data['title'],
                    article_data.get('date'),
                    article_data.get('category'),
                    article_data.get('preview_content'),
                    article_data.get('full_content'),
                    article_data['url']
                ))
                article_id = existing[0]
            else:
                cursor.execute('''
                    INSERT INTO news_articles (title, url, date, category, content_text, full_content)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    article_data['title'],
                    article_data['url'],
                    article_data.get('date'),
                    article_data.get('category'),
                    article_data.get('preview_content'),
                    article_data.get('full_content')
                ))
                article_id = cursor.lastrowid
            
            cursor.execute('DELETE FROM news_search_index WHERE article_id = ?', (article_id,))

            search_text = f"{article_data['title']} {article_data.get('category', '')} {article_data.get('preview_content', '')}"
            keywords = ' '.join(re.findall(r'\b\w{3,}\b', search_text.lower()))
            
            cursor.execute('''
                INSERT INTO news_search_index (article_id, keywords)
                VALUES (?, ?)
            ''', (article_id, keywords))
            
            conn.commit()
            return article_id
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Ошибка сохранения статьи: {str(e)}")
            return None
        finally:
            conn.close()
    
    def log_update(self, processed_count, new_articles_count):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO update_log (articles_processed, new_articles)
            VALUES (?, ?)
        ''', (processed_count, new_articles_count))
        
        conn.commit()
        conn.close()
    
    def search_articles(self, keyword, limit=1100):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                na.title,
                na.url,
                na.date,
                na.category,
                na.content_text,
                na.full_content
            FROM news_articles na
            JOIN news_search_index nsi ON na.id = nsi.article_id
            WHERE na.title LIKE ? OR nsi.keywords LIKE ? OR na.category LIKE ?
            ORDER BY na.created_at DESC
            LIMIT ?
        ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', limit))
        
        results = cursor.fetchall()
        conn.close()
        
        articles = []
        for title, url, date, category, content_text, full_content in results:
            articles.append({
                'title': title,
                'url': url,
                'date': date,
                'category': category,
                'preview_content': content_text,
                'full_content': full_content
            })
        
        return articles
    
    def get_stats(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM news_articles')
        total_articles = cursor.fetchone()[0]
        
        cursor.execute('SELECT last_update FROM update_log ORDER BY id DESC LIMIT 1')
        last_update_result = cursor.fetchone()
        last_update = last_update_result[0] if last_update_result else None
        
        conn.close()
        
        return {
            'total_articles': total_articles,
            'last_update': last_update
        }
    def article_exists(self, url):
        """Проверяет, существует ли статья с указанным URL в базе данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM news_articles WHERE url = ?', (url,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

async def fetch_news_from_source(max_pages=50):
    from articles_search import parse_news_card
    import requests
    
    found_articles = []
    logger.info("🔄 Начинаем парсинг новостей с сайта...")
    
    for page in range(1, max_pages + 1):
        try:
            url = f"https://mir.pravo.by/news/?PAGEN_1={page}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            news_container = soup.find('div', id='news-container')
            
            if not news_container:
                if page >= 3:
                    break
                continue

            news_cards = news_container.find_all('div', class_='news-single-item')

            if not news_cards:
                break

            for card in news_cards:
                article_data = parse_news_card(card)
                if article_data:
                    if news_db.article_exists(article_data['url']):
                        logger.info(f"✅ Найдена существующая статья, парсинг завершен. Всего собрано {len(found_articles)} новых статей")
                        return found_articles
                    
                    found_articles.append(article_data)

            if len(found_articles) >= 1100:
                break
                
        except Exception as e:
            continue
    
    logger.info(f"✅ Парсинг завершен. Всего найдено {len(found_articles)} статей")
    return found_articles

async def update_news_database():
    """Обновляет базу данных новостей"""
    if not news_db.needs_update():
        logger.info("База данных новостей актуальна, пропускаем обновление")
        return {
            'processed': 0,
            'new_articles': 0,
            'status': 'already_updated'
        }
    
    logger.info("🔄 Начинаем обновление базы данных новостей...")

    articles = await fetch_news_from_source(max_pages=50)
    
    total_processed = 0
    total_new = 0
    
    for article in articles:
        try:
            content_data = await news_db.parse_article_content(article['url'])
            if content_data:
                article.update(content_data)
            
            article_id = news_db.save_article(article)
            if article_id:
                total_new += 1
            
            total_processed += 1
            
        except Exception as e:
            continue
    
    news_db.log_update(total_processed, total_new)
    logger.info(f"✅ База данных обновлена. Обработано: {total_processed}, Новых: {total_new}")
    
    return {
        'processed': total_processed,
        'new_articles': total_new,
        'status': 'updated'
    }

def create_notifications_table():
    try:
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_notifications (
                user_id INTEGER PRIMARY KEY,
                notifications_enabled BOOLEAN DEFAULT FALSE,
                last_notified_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ Таблица user_notifications создана или уже существует")
        return True
    except Exception as e:
        print(f"❌ Ошибка создания таблицы user_notifications: {e}")
        return False

def search_news_in_database(keyword, limit=1100):
    return news_db.search_articles(keyword, limit)

def get_articles_after_date(date_string: str):
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT title, url, date, category 
        FROM news 
        WHERE datetime(parsed_at) > datetime(?)
        ORDER BY parsed_at DESC
        LIMIT 10
    ''', (date_string,))
    
    articles = cursor.fetchall()
    conn.close()
    
    return [{
        'title': article[0],
        'url': article[1],
        'date': article[2],
        'category': article[3]
    } for article in articles]

news_db = NewsDatabase()