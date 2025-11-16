from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

news_router = Router()

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
        
        # Дата публикации - ищем div с классом news-single-date
        date_elem = card.find('div', class_='news-single-date')
        if date_elem:
            article_data['date'] = date_elem.get_text(strip=True)
        
        # Категория новости - ищем div с классом arhive-section-title
        category_elem = card.find('div', class_='arhive-section-title')
        if category_elem:
            category_text = category_elem.get_text(strip=True)
            article_data['category'] = category_text.replace('·', '').strip()
        
        return article_data
        
    except Exception as e:
        print(f"❌ Ошибка парсинга карточки: {str(e)}")
        return None

async def search_news_by_keyword(keyword, max_pages=50, target_count=15):
    found_articles = []
    
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
                print(f"❌ Контейнер новостей не найден на странице {page}")
                if page >= 3:
                    print("🚫 Контейнер не найден на 3 страницах подряд, останавливаем поиск")
                    break
                continue

            news_cards = news_container.find_all('div', class_='news-single-item')
            
            print(f"📄 Страница {page}: найдено {len(news_cards)} карточек новостей")

            if not news_cards:
                print(f"🚫 На странице {page} нет карточек новостей, останавливаем поиск")
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

                    if len(found_articles) >= target_count:
                        print(f"🎯 Найдено {len(found_articles)} статей, останавливаем поиск")
                        return found_articles
            
            if page == 51:
                break

            print(f"📊 Итого: страница {page} - найдено {len(found_articles)} подходящих статей")
            
        except Exception as e:
            print(f"❌ Ошибка на странице {page}: {str(e)}")
            continue
    
    print(f"✅ Поиск завершен. Всего найдено {len(found_articles)} статей")
    return found_articles

def create_articles_keyboard(articles):
    builder = InlineKeyboardBuilder()
    
    for i, article in enumerate(articles):
        title = article['title']
        preview = title[:35] + "..." if len(title) > 35 else title
        
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
    
    await message.answer("🔍 Ищу статьи... Это может занять несколько секунд")
    
    articles = await search_news_by_keyword(keyword, max_pages=400, target_count=15)
    
    if not articles:
        await message.answer(
            f"❌ Статьи с ключевым словом '{keyword}' не найдены",
            reply_markup=get_back_button()
        )
        await state.clear()
        return
    
    # Сохраняем статьи в состоянии
    await state.update_data({
        'articles': articles,
        'keyword': keyword
    })
    
    # Показываем найденные статьи для выбора
    keyboard = create_articles_keyboard(articles)
    
    message_text = f"🔍 Найдено {len(articles)} статей с ключевым словом '{keyword}':\n\nВыберите статью:"
    
    await message.answer(
        message_text,
        reply_markup=keyboard
    )

@news_router.callback_query(Operation.waiting_for_article_selection, F.data.startswith("article_"))
async def show_article_link(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data['articles']
    
    # Получаем индекс выбранной статьи
    article_index = int(callback.data.split("_")[1])
    article = articles[article_index]
    
    # Формируем сообщение со ссылкой
    response_text = (
        f"📰 {article['title']}\n\n"
    )
    
    if article.get('date'):
        response_text += f"📅 Дата: {article['date']}\n\n"
    
    if article.get('description'):
        desc = article['description']
        if len(desc) > 200:
            desc = desc[:200] + "..."
        response_text += f"📝 Описание: {desc}\n\n"
    
    response_text += f"🔗 Ссылка на статью: {article['url']}"
    
    # Создаем клавиатуру для возврата
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
        disable_web_page_preview=False  # Разрешаем превью ссылки
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
