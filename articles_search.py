from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import requests
from bs4 import BeautifulSoup
from databases.news_database import news_db, update_news_database, search_news_in_database
import asyncio
from datetime import datetime
import sqlite3
from databases.news_database import create_notifications_table

print("🔄 Создаем таблицу уведомлений...")
create_notifications_table()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

news_router = Router()

@news_router.startup()
async def on_startup():
    logger.info("Проверяем обновление базы данных новостей...")
    await update_news_database()
    
    create_notifications_table()

    asyncio.create_task(check_and_send_notifications())

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

async def get_full_article_content(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')

        content_div = soup.find('div', class_='news-detail-text')
        if not content_div:
            content_div = soup.find('div', class_='news-text')
        if not content_div:
            content_div = soup.find('article')
        
        if content_div:
            for element in content_div.find_all(['script', 'style', 'aside', 'nav']):
                element.decompose()
            
            text = content_div.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            return '\n'.join(lines)
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка при получении полного текста статьи: {e}")
        return None

async def search_news_by_keyword(keyword, max_pages=50, target_count=20):
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
                    full_content = await get_full_article_content(article['url'])
                    if full_content:
                        article['full_content'] = full_content
                        article['preview_content'] = full_content[:300] + "..." if len(full_content) > 300 else full_content
                    
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

def create_article_actions_keyboard(article_index, has_full_content=False):
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="🔗 Перейти к статье",
        url=f"article_url_{article_index}"
    ))
    
    if has_full_content:
        builder.add(InlineKeyboardButton(
            text="📖 Показать полный текст",
            callback_data=f"full_text_{article_index}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к списку",
        callback_data="back_to_articles_list"
    ))
    
    builder.add(InlineKeyboardButton(
        text="🔄 Новый поиск",
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
async def show_article_options(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data['articles']

    article_index = int(callback.data.split("_")[1])
    article = articles[article_index]

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
    
    response_text += "Выберите действие:"

    has_full_content = bool(article.get('full_content'))
    keyboard = create_article_actions_keyboard(article_index, has_full_content)
 
    keyboard_json = keyboard.model_dump()
    for button_row in keyboard_json['inline_keyboard']:
        for button in button_row:
            if button.get('text') == "🔗 Перейти к статье":
                button['url'] = article['url']
    
    final_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_json['inline_keyboard'])
    
    await callback.message.edit_text(
        text=response_text,
        reply_markup=final_keyboard,
        disable_web_page_preview=False
    )

def split_text_into_parts(text, max_length=4000):
    """Разбивает текст на части с учетом границ предложений"""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    # Разбиваем по предложениям
    sentences = text.split('. ')
    
    for sentence in sentences:
        # Если текущая часть + новое предложение превышает лимит
        if len(current_part) + len(sentence) + 2 > max_length:
            if current_part:
                parts.append(current_part.strip())
                current_part = ""
            
            # Если одно предложение слишком длинное, разбиваем его
            if len(sentence) > max_length:
                words = sentence.split(' ')
                for word in words:
                    if len(current_part) + len(word) + 1 > max_length:
                        if current_part:
                            parts.append(current_part.strip())
                            current_part = ""
                    current_part += word + " "
            else:
                current_part = sentence + ". "
        else:
            current_part += sentence + ". "
    
    if current_part.strip():
        parts.append(current_part.strip())
    
    return parts

@news_router.callback_query(Operation.waiting_for_article_selection, F.data.startswith("full_text_"))
async def show_full_article_text(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data['articles']

    article_index = int(callback.data.split("_")[2])
    article = articles[article_index]
    
    if not article.get('full_content'):
        await callback.answer("❌ Полный текст статьи недоступен", show_alert=True)
        return
    
    full_content = article['full_content']
    
    # Разбиваем текст на части если он слишком длинный
    if len(full_content) > 4000:
        parts = []
        current_part = ""
        
        for paragraph in full_content.split('\n'):
            if len(current_part) + len(paragraph) + 1 < 4000:
                current_part += paragraph + '\n'
            else:
                parts.append(current_part)
                current_part = paragraph + '\n'
        
        if current_part:
            parts.append(current_part)

        await callback.message.edit_text(
            text=f"📖 {article['title']}\n\n{parts[0]}",
            reply_markup=create_full_text_navigation(article_index, 0, len(parts))
        )
    else:
        await callback.message.edit_text(
            text=f"📖 {article['title']}\n\n{full_content}",
            reply_markup=create_full_text_back_button(article_index)
        )

def create_full_text_navigation(article_index, current_part, total_parts):
    builder = InlineKeyboardBuilder()
    
    navigation_buttons = []
    
    if current_part > 0:
        navigation_buttons.append(InlineKeyboardButton(
            text="⬅️ Предыдущая",
            callback_data=f"text_part_{article_index}_{current_part-1}"
        ))
    
    if current_part < total_parts - 1:
        navigation_buttons.append(InlineKeyboardButton(
            text="Следующая ➡️",
            callback_data=f"text_part_{article_index}_{current_part+1}"
        ))
    
    if navigation_buttons:
        builder.row(*navigation_buttons)
    
    builder.row(InlineKeyboardButton(
        text="🔙 Назад к статье",
        callback_data=f"article_{article_index}"
    ))
    
    return builder.as_markup()

def create_full_text_back_button(article_index):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к статье",
        callback_data=f"article_{article_index}"
    ))
    return builder.as_markup()

@news_router.callback_query(Operation.waiting_for_article_selection, F.data.startswith("text_part_"))
async def navigate_full_text(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    articles = data['articles']

    parts = callback.data.split("_")
    article_index = int(parts[2])
    part_index = int(parts[3])
    
    article = articles[article_index]
    full_content = article['full_content']
    
    content_parts = []
    current_part = ""
    
    for paragraph in full_content.split('\n'):
        if len(current_part) + len(paragraph) + 1 < 4000:
            current_part += paragraph + '\n'
        else:
            content_parts.append(current_part)
            current_part = paragraph + '\n'
    
    if current_part:
        content_parts.append(current_part)
    
    if part_index < len(content_parts):
        await callback.message.edit_text(
            text=f"📖 {article['title']} (часть {part_index + 1}/{len(content_parts)})\n\n{content_parts[part_index]}",
            reply_markup=create_full_text_navigation(article_index, part_index, len(content_parts))
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

def enable_user_notifications(user_id: int):
    try:
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_notifications 
            (user_id, notifications_enabled, last_notified_date)
            VALUES (?, TRUE, ?)
        ''', (user_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except sqlite3.OperationalError as e:
        print(f"Таблица не найдена, создаем... Ошибка: {e}")
        create_notifications_table()
        return False
    except Exception as e:
        print(f"Другая ошибка: {e}")
        return False
    
def disable_user_notifications(user_id: int):
    try:
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_notifications 
            (user_id, notifications_enabled, last_notified_date)
            VALUES (?, FALSE, ?)
        ''', (user_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except sqlite3.OperationalError:
        create_notifications_table()
        return False

def get_users_with_notifications():
    try:
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, last_notified_date 
            FROM user_notifications 
            WHERE notifications_enabled = TRUE
        ''')
        users = cursor.fetchall()
        conn.close()
        return users
    except sqlite3.OperationalError:
        create_notifications_table()
        return []
    
def update_last_notified_date(user_id: int):
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_notifications 
        SET last_notified_date = ?
        WHERE user_id = ?
    ''', (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

@news_router.callback_query(F.data == 'notification_on')
async def enable_notifications(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Пытаемся включить уведомления
    success = enable_user_notifications(user_id)
    
    if success:
        await callback.message.edit_text(
            text="✅ Уведомления включены! Вы будете получать уведомления о новых новостях.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='🔕 Отключить уведомления', callback_data='notification_off')
            ]])
        )
    else:
        # Если не удалось, пробуем еще раз (таблица должна быть создана)
        success_retry = enable_user_notifications(user_id)
        if success_retry:
            await callback.message.edit_text(
                text="✅ Уведомления включены! Вы будете получать уведомления о новых новостях.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='🔕 Отключить уведомления', callback_data='notification_off')
                ]])
            )
        else:
            await callback.message.edit_text(
                text="❌ Не удалось включить уведомления. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='🔄 Попробовать снова', callback_data='notification_on')
                ]])
            )

@news_router.callback_query(F.data == 'notification_off')
async def disable_notifications(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    disable_user_notifications(user_id)
    
    await callback.message.edit_text(
        text="❌ Уведомления отключены. Вы больше не будете получать уведомления о новых новостях.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='💡 Включить уведомления', callback_data='notification_on')
        ]])
    )

async def check_and_send_notifications():
    while True:
        try:
            update_result = await update_news_database()
            
            if update_result['status'] == 'updated' and update_result['new_articles'] > 0:
                users = get_users_with_notifications()
                
                for user_id, last_notified_date in users:
                    try:
                        new_articles = get_articles_after_date(last_notified_date)
                        
                        if new_articles:
                            message_text = f"📢 Появились новые новости! ({len(new_articles)} шт.)\n\n"
                            message_text += "Для просмотра используйте поиск или обновите базу данных."
                            
                            await bot.send_message(
                                chat_id=user_id,
                                text=message_text,
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                    InlineKeyboardButton(text='🔍 Поиск новостей', callback_data='state_search'),
                                    InlineKeyboardButton(text='🔄 Обновить базу', callback_data='update_news_db')
                                ]])
                            )
                            
                            update_last_notified_date(user_id)
                            
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
                        continue
            
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче уведомлений: {e}")
            await asyncio.sleep(3000)

def get_articles_after_date(date_string: str):
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT title, url, date, category 
        FROM news_articles 
        WHERE datetime(created_at) > datetime(?)
        ORDER BY created_at DESC
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

@news_router.callback_query(F.data == 'back_main_menu')
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = callback.from_user.id
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('SELECT notifications_enabled FROM user_notifications WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    notifications_enabled = result[0] if result else False
    
    notification_button = InlineKeyboardButton(
        text='🔕 Отключить уведомления' if notifications_enabled else '💡 Включить уведомления',
        callback_data='notification_off' if notifications_enabled else 'notification_on'
    )
    
    main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔍 Поиск новостей', callback_data='state_search')],
        [InlineKeyboardButton(text='🔄 Обновить базу новостей', callback_data='update_news_db')],
        [notification_button],
        [InlineKeyboardButton(text='ℹ️ Помощь', callback_data='help')]
    ])
    
    status_text = "🔔 Уведомления включены" if notifications_enabled else "🔕 Уведомления отключены"
    
    await callback.message.edit_text(
        text=f"📰 Главное меню\n\n{status_text}",
        reply_markup=main_menu_keyboard
    )