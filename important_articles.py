from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import requests
from bs4 import BeautifulSoup
from articles_search import parse_news_card

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()

important_news_router = Router()

async def parse_important_articles():
    """Парсит важные статьи с главной страницы"""
    try:
        url = "https://mir.pravo.by/news/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print(f"🔍 Загружаю страницу: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        print(f"📄 Заголовок страницы: {soup.title.string if soup.title else 'Нет заголовка'}")
        
        important_articles = []

        news_cards = soup.find_all('div', class_='news-single-item')
        print(f"🔍 Найдено всего карточек: {len(news_cards)}")

        for i, card in enumerate(news_cards):
            print(f"🔍 Обрабатываю карточку {i+1}")
            article_data = parse_news_card(card)
            if article_data:
                print(f"✅ Успешно распарсена: {article_data['title'][:50]}...")
                important_articles.append(article_data)
            else:
                print("❌ Не удалось распарсить карточку")
        
        print(f"📊 Итого найдено статей: {len(important_articles)}")
        return important_articles[:10] 
    
    except Exception as e:
        print(f"❌ Ошибка при парсинге важных статей: {str(e)}")
        import traceback
        traceback.print_exc()
        return []
    
def create_important_articles_keyboard(articles):
    builder = InlineKeyboardBuilder()
    
    for i, article in enumerate(articles, 1):
        # Обрезаем заголовок для кнопки
        title = article['title']
        preview = title[:30] + "..." if len(title) > 30 else title
        
        builder.add(InlineKeyboardButton(
            text=f"📰 {i}. {preview}",
            callback_data=f"important_{i-1}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад в меню",
        callback_data="back_main_menu"
    ))
    
    builder.adjust(1)
    return builder.as_markup()

@important_news_router.callback_query(F.data == 'top_states')
async def show_important_articles(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📡 Загружаю важные статьи...")
    
    articles = await parse_important_articles()
    
    if not articles:
        await callback.message.edit_text(
            "❌ Не удалось загрузить важные статьи",
            reply_markup=get_back_button()
        )
        return
    
    # Сохраняем статьи в состоянии
    await state.update_data({
        'important_articles': articles
    })

    keyboard = create_important_articles_keyboard(articles)
    
    message_text = "Важные статьи:\n\n"
    for i, article in enumerate(articles, 1):
        message_text += f"{i}. {article['title']}\n"
    
    await callback.message.edit_text(
        text=message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@important_news_router.callback_query(F.data.startswith("important_"))
async def show_important_article(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data.get('important_articles', [])
    
    if not articles:
        await callback.answer("❌ Статьи не найдены")
        return
    
    article_index = int(callback.data.split("_")[1])
    
    if article_index >= len(articles):
        await callback.answer("❌ Статья не найдена")
        return
    
    article = articles[article_index]
    
    response_text = (
        f"🔥 {article['title']}\n\n"
    )
    
    if article.get('date'):
        response_text += f"📅 Дата: {article['date']}\n\n"
    
    if article.get('category'):
        response_text += f"📂 Категория: {article['category']}\n\n"
    
    response_text += f"🔗 Ссылка на статью: {article['url']}"

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к списку статей",
        callback_data="back_to_important_list"
    ))
    builder.add(InlineKeyboardButton(
        text="🏠 В главное меню",
        callback_data="back_main_menu"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=response_text,
        reply_markup=builder.as_markup(),
        disable_web_page_preview=False,
        parse_mode="Markdown"
    )

@important_news_router.callback_query(F.data == "back_to_important_list")
async def back_to_important_list(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data.get('important_articles', [])
    
    if not articles:
        await callback.message.edit_text(
            "❌ Статьи не найдены",
            reply_markup=get_back_button()
        )
        return
    
    keyboard = create_important_articles_keyboard(articles)
    
    message_text = "🔥 Важные статьи:\n\n"
    for i, article in enumerate(articles, 1):
        message_text += f"{i}. {article['title']}\n"
    
    await callback.message.edit_text(
        text=message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@important_news_router.callback_query(F.data == 'important_states')
async def show_important_articles(callback: types.CallbackQuery, state: FSMContext):
    print("🔔 Обработчик important_states вызван!")  # Добавить эту строку
    await callback.message.edit_text("📡 Загружаю важные статьи...")

def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Назад', callback_data='back_main_menu')]
    ])
