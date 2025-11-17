from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import requests
from bs4 import BeautifulSoup
from news_database import news_db, update_news_database, search_news_in_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

news_router = Router()

@news_router.startup()
async def on_startup():
    """Автоматически обновляет базу данных при старте"""
    logger.info("Проверяем обновление базы данных новостей...")
    await update_news_database()

class Operation(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_selection = State()
    waiting_for_article_selection = State()

def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Назад', callback_data='back_main_menu')]
    ])

def parse_news_card(card):
    try:
        article_data = {}
        
        title_elem = card.find('h4', class_='news-single-title')
        if title_elem:
            link_elem = title_elem.find('a')
            if link_elem:
                article_data['title'] = link_elem.get_text(strip=True)
            else:
                article_data['title'] = title_elem.get_text(strip=True)
        else:
            return None
        
        # Ссылка на новость
        link_elem = card.find('a', href=True)
        if link_elem:
            href = link_elem['href']
            if href.startswith('/'):
                href = f"https://mir.pravo.by{href}"
            article_data['url'] = href
        else:
            return None
        
        date_elem = card.find('div', class_='news-single-date')
        if date_elem:
            article_data['date'] = date_elem.get_text(strip=True)
        
        category_elem = card.find('div', class_='arhive-section-title')
        if category_elem:
            category_text = category_elem.get_text(strip=True)
            article_data['category'] = category_text.replace('·', '').strip()
        
        return article_data
        
    except Exception as e:
        print(f"❌ Ошибка парсинга карточки: {str(e)}")
        return None

async def search_news_by_keyword(keyword, max_pages=50, target_count=20):
    """Ищет новости по ключевому слову"""
    found_articles = []
    logger.info(f"🔍 Начинаем поиск статей по ключевому слову: {keyword}")
    
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

            page_articles = []
            for card in news_cards:
                article_data = parse_news_card(card)
                if article_data:
                    page_articles.append(article_data)
            
            for article in page_articles:
                title = article.get('title', '').lower()
                category = article.get('category', '').lower()
                
                if (keyword.lower() in title or keyword.lower() in category):
                    found_articles.append(article)

                    if len(found_articles) >= 20:
                        logger.info(f"✅ Найдено {len(found_articles)} статей, останавливаем поиск")
                        return found_articles
            
            if page == 50:
                break
            
        except Exception as e:
            continue
    
    logger.info(f"✅ Поиск завершен. Всего найдено {len(found_articles)} статей")
    return found_articles

def create_articles_keyboard(articles):
    builder = InlineKeyboardBuilder()

    limited_articles = articles[:20]
    
    for i, article in enumerate(limited_articles):
        title = article['title']
        preview = title[:30] + "..." if len(title) > 30 else title
        
        builder.add(InlineKeyboardButton(
            text=f"📰 {i+1}. {preview}",
            callback_data=f"article_{i}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к поиску",
        callback_data="back_to_news_search"
    ))
    
    builder.adjust(1)
    return builder.as_markup()

@news_router.callback_query(F.data == 'state_search')
async def state_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text='🔎 Введите ключевые слова для поиска статей...', 
        reply_markup=get_back_button()
    )
    await state.set_state(Operation.waiting_for_article_selection)


@news_router.message(Operation.waiting_for_article_selection)
async def process_news_keyword(message: types.Message, state: FSMContext):
    keyword = message.text.strip()
    
    if not keyword:
        await message.answer("Пожалуйста, введите ключевое слово для поиска.")
        return
    
    await message.answer("🔍 Ищу статьи в базе данных...")
    
    articles = search_news_in_database(keyword)
    
    if articles:
        source_info = "📚 (из базы данных)"
    else:
        # Если в базе нет, ищем на сайте
        await message.answer("🔄 Статьи не найдены в базе. Ищу на сайте...")
        articles = await search_news_by_keyword(keyword, max_pages=10, target_count=15)
        source_info = "🌐 (с сайта)"
    
    if not articles:
        await message.answer(
            f"❌ Статьи с ключевым словом '{keyword}' не найдены",
            reply_markup=get_back_button()
        )
        await state.clear()
        return

    await state.update_data({
        'articles': articles,
        'keyword': keyword
    })

    limited_articles = articles[:20]
    keyboard = create_articles_keyboard(limited_articles)
    
    message_text = f"🔍 Найдено {len(articles)} статей с ключевым словом '{keyword}' {source_info}:\n\n"
    message_text += f"📋 Показано первых {len(limited_articles)} статей:\n\nВыберите статью:"
    
    await message.answer(
        message_text,
        reply_markup=keyboard
    )

@news_router.callback_query(Operation.waiting_for_article_selection, F.data.startswith("article_"))
async def show_article_link(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data['articles']

    article_index = int(callback.data.split("_")[1])
    article = articles[article_index]
    
    # Формируем сообщение со ссылкой и контентом
    response_text = f"📰 {article['title']}\n\n"
    
    if article.get('date'):
        response_text += f"📅 Дата: {article['date']}\n"
    
    if article.get('category'):
        response_text += f"🏷️ Категория: {article['category']}\n"
    
    response_text += "\n"

    if article.get('preview_content'):
        response_text += f"📝 {article['preview_content']}\n\n"
    elif article.get('full_content'):
        full_content = article['full_content']
        preview = full_content[:300] + "..." if len(full_content) > 300 else full_content
        response_text += f"📝 {preview}\n\n"
    
    response_text += f"🔗 Ссылка на статью: {article['url']}"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к списку статей",
        callback_data="back_to_articles_list"
    ))
    builder.add(InlineKeyboardButton(
        text="🔄 Новый поиск",
        callback_data="back_to_news_search"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=response_text,
        reply_markup=builder.as_markup(),
        disable_web_page_preview=False
    )

@news_router.callback_query(Operation.waiting_for_article_selection, F.data == "back_to_articles_list")
async def back_to_articles_list(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data['articles']
    keyword = data['keyword']
    
    keyboard = create_articles_keyboard(articles)
    
    await callback.message.edit_text(
        f"🔍 Найдено {len(articles)} статей с ключевым словом '{keyword}':\n\nВыберите статью:",
        reply_markup=keyboard
    )

@news_router.callback_query(Operation.waiting_for_article_selection, F.data == "back_to_news_search")
async def back_to_news_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text='🔎 Введите ключевые слова для поиска статей...', 
        reply_markup=get_back_button()
    )

@news_router.callback_query(F.data == "update_news_db")
async def force_update_news_db(callback: types.CallbackQuery):
    await callback.message.answer("🔄 Принудительное обновление базы данных новостей...")
    
    result = await update_news_database()
    
    if result['status'] == 'already_updated':
        message = "✅ База данных уже актуальна, обновление не требуется"
    elif result['status'] == 'updated':
        stats = news_db.get_stats()
        message = (
            f"✅ База данных обновлена!\n"
            f"📊 Обработано статей: {result['processed']}\n"
            f"🆕 Новых статей: {result['new_articles']}\n"
            f"📚 Всего в базе: {stats['total_articles']}\n"
            f"🕐 Последнее обновление: {stats['last_update']}"
        )
    else:
        message = "❌ Ошибка при обновлении базы данных"
    
    await callback.message.answer(message)