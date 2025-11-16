from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3
import logging
import asyncio
import requests
from bs4 import BeautifulSoup
import re
import articles_search
from articles_search import parse_news_card, news_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
callback_router = Router()
dp.include_router(news_router)

class Operation(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_selection = State()
    waiting_for_article_selection = State()

async def parse_etalonline_by_document():
    try:
        url = f"https://etalonline.by/document/?regnum=v19302570&q_id=4416393"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        section_element = soup.find('div', class_='Section1')
        
        if section_element:
            # Получаем весь текст с пробелами между элементами
            all_text = section_element.get_text(separator=' ', strip=True)
            
            # Очищаем текст от лишних пробелов
            cleaned_text = re.sub(r'\s+', ' ', all_text).strip()
            
            return {
                'success': True,
                'text': cleaned_text,
                'url': url
            }
        else:
            return {
                'success': False,
                'error': 'Элемент с классом Section1 не найден на странице'
            }
            
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'Ошибка подключения к сайту: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Ошибка при парсинге: {str(e)}'
        }

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💡 Поиск в конституции', callback_data='konstitution_search')],
        [InlineKeyboardButton(text='🔎 Поиск статей', callback_data='state_search')],
        [InlineKeyboardButton(text='⤴ Важные статьи', callback_data='top_states')],
        [InlineKeyboardButton(text='🎮 Правовая игра', callback_data='pravo_game')],
    ])

def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Назад', callback_data='back_main_menu')]
    ])

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "👋 Добро пожаловать!\n\n"
        "Выберите нужный раздел в меню ниже:"
    )
    
    await message.answer(
        text=welcome_text,
        reply_markup=get_main_menu()
    )
    
@dp.message(Command('menu'))
async def open_menu(message: types.Message):
    await message.answer('📋 Главное меню. Выберите раздел:', reply_markup=get_main_menu())

@dp.callback_query(F.data == 'konstitution_search')
async def konstitution_search(callback: types.CallbackQuery, state: FSMContext ):
    await callback.message.edit_text(text='⌛ Введите ключевые слова для поиска...', reply_markup=get_back_button())
    await state.set_state(Operation.waiting_for_keyword)

def create_sentences_keyboard(sentences):
    builder = InlineKeyboardBuilder()
    
    for i, sent_data in enumerate(sentences):
        # Обрезаем предложение для отображения в кнопке
        preview = sent_data['sentence'][:40] + "..." if len(sent_data['sentence']) > 40 else sent_data['sentence']
        builder.add(InlineKeyboardButton(
            text=f"📌 {i+1}. {preview}",
            callback_data=f"sentence_{i}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к поиску",
        callback_data="back_to_search"
    ))
    
    builder.adjust(1)
    return builder.as_markup()

def truncate_text(text, max_length=4000):
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def find_sentences_with_keyword(text, keyword):
    # Разбиваем текст на предложения
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    found_sentences = []
    
    for i, sentence in enumerate(sentences):
        if keyword.lower() in sentence.lower():
            # Сохраняем индекс предложения и само предложение
            found_sentences.append({
                'index': i,
                'sentence': sentence,
                'context_before': sentences[max(0, i-2):i] if i > 0 else [],
                'context_after': sentences[i+1:min(len(sentences), i+3)] if i < len(sentences)-1 else []
            })
    
    return found_sentences

@dp.message(Operation.waiting_for_keyword)
async def process_keyword(message: types.Message, state: FSMContext):
    keyword = message.text.strip()
    
    if not keyword:
        await message.answer("Пожалуйста, введите ключевое слово для поиска.")
        return
    
    await message.answer("🔍 Ищу информацию...")

    result = await parse_etalonline_by_document()
    
    if not result['success']:
        await message.answer(
            f"❌ Не удалось найти информацию: {result['error']}",
            reply_markup=get_back_button()
        )
        await state.clear()
        return
    
    # Ищем предложения с ключевым словом
    sentences_data = find_sentences_with_keyword(result['text'], keyword)
    
    if not sentences_data:
        await message.answer(
            f"❌ Предложений с ключевым словом '{keyword}' не найдено",
            reply_markup=get_back_button()
        )
        await state.clear()
        return
    
    # Сохраняем данные в состоянии
    await state.update_data({
        'sentences_data': sentences_data,
        'keyword': keyword,
        'full_text': result['text'],
        'url': result['url']
    })
    
    # Показываем найденные предложения для выбора
    keyboard = create_sentences_keyboard(sentences_data, keyword)
    
    message_text = f"🔍 Найдено {len(sentences_data)} предложений с ключевым словом '{keyword}':\n\nВыберите предложение для просмотра контекста:"
    
    await message.answer(
        truncate_text(message_text),
        reply_markup=keyboard
    )
    
    await state.set_state(Operation.waiting_for_selection)

@dp.callback_query(Operation.waiting_for_selection, F.data.startswith("sentence_"))
async def show_sentence_context(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sentences_data = data['sentences_data']
    
    # Получаем индекс выбранного предложения
    sentence_index = int(callback.data.split("_")[1])
    sent_data = sentences_data[sentence_index]
    
    # Сохраняем индекс выбранного предложения в состоянии
    await state.update_data({
        'selected_sentence_index': sentence_index
    })
    
    context_parts = []
    
    context_parts.append("🎯 **Найденное предложение:**")
    context_parts.append(f"{sent_data['sentence']}")
    context_parts.append("")
    
    context_text = "\n".join(context_parts)
    
    builder = InlineKeyboardBuilder()
    
    if sent_data['context_before']:
        builder.add(InlineKeyboardButton(
            text="⬅️ Предыдущий контекст",
            callback_data=f"context_prev_{sentence_index}"
        ))
    
    if sent_data['context_after']:
        builder.add(InlineKeyboardButton(
            text="Следующий контекст ➡️",
            callback_data=f"context_next_{sentence_index}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к списку",
        callback_data="back_to_sentences_list"
    ))
    builder.add(InlineKeyboardButton(
        text="🔄 Новый поиск",
        callback_data="back_to_search"
    ))
    
    builder.adjust(1)
    
    try:
        await callback.message.edit_text(
            text=context_text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback.message.edit_text(
            text=context_text,
            reply_markup=builder.as_markup()
        )

# Обработчик для просмотра предыдущего контекста
@dp.callback_query(Operation.waiting_for_selection, F.data.startswith("context_prev_"))
async def show_previous_context(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sentences_data = data['sentences_data']
    
    sentence_index = int(callback.data.split("_")[2])
    sent_data = sentences_data[sentence_index]
    
    context_parts = []

    if sent_data['context_before']:
        context_parts.append("📝 Предыдущий контекст:")
        for before_sent in sent_data['context_before']:
            context_parts.append(f"• {before_sent}")
    
    context_text = "\n".join(context_parts) if context_parts else "❌ Предыдущий контекст отсутствует"
    
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="↩️ К основному предложению",
        callback_data=f"sentence_{sentence_index}"
    ))
    
    if sent_data['context_after']:
        builder.add(InlineKeyboardButton(
            text="Следующий контекст ➡️",
            callback_data=f"context_next_{sentence_index}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 К списку предложений",
        callback_data="back_to_sentences_list"
    ))
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=context_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработчик для просмотра следующего контекста
@dp.callback_query(Operation.waiting_for_selection, F.data.startswith("context_next_"))
async def show_next_context(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sentences_data = data['sentences_data']
    
    sentence_index = int(callback.data.split("_")[2])
    sent_data = sentences_data[sentence_index]
    
    context_parts = []

    if sent_data['context_after']:
        context_parts.append("📝 Следующий контекст:")
        for after_sent in sent_data['context_after']:
            context_parts.append(f"• {after_sent}")
    
    context_text = "\n".join(context_parts) if context_parts else "❌ Следующий контекст отсутствует"
    
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="↩️ К основному предложению",
        callback_data=f"sentence_{sentence_index}"
    ))
    
    if sent_data['context_before']:
        builder.add(InlineKeyboardButton(
            text="⬅️ Предыдущий контекст",
            callback_data=f"context_prev_{sentence_index}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 К списку предложений",
        callback_data="back_to_sentences_list"
    ))
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        text=context_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@dp.callback_query(Operation.waiting_for_selection, F.data == "back_to_search")
async def back_to_search_from_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text='Введите ключевые слова для поиска...', 
        reply_markup=get_back_button()
    )
    await state.set_state(Operation.waiting_for_keyword)

async def send_long_message(message, text, reply_markup=None):
    """Разбивает длинное сообщение на части"""
    max_length = 4000
    
    if len(text) <= max_length:
        await message.answer(text, reply_markup=reply_markup)
        return
    
    # Разбиваем текст на части
    parts = []
    current_part = ""
    
    for sentence in text.split('. '):
        if len(current_part) + len(sentence) + 2 <= max_length:
            current_part += sentence + '. '
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = sentence + '. '
    
    if current_part:
        parts.append(current_part.strip())
    
    # Отправляем части
    for i, part in enumerate(parts):
        if i == len(parts) - 1 and reply_markup:
            await message.answer(part, reply_markup=reply_markup)
        else:
            await message.answer(part)

# Обновляем обработчик для использования новой функции
@dp.callback_query(Operation.waiting_for_selection, F.data == "back_to_sentences_list")
async def back_to_sentences_list(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sentences_data = data['sentences_data']
    keyword = data['keyword']
    
    keyboard = create_sentences_keyboard(sentences_data, keyword)
    
    message_text = f"🔍 Найдено {len(sentences_data)} предложений с ключевым словом '{keyword}':\n\nВыберите предложение для просмотра контекста:"
    
    await callback.message.edit_text(
        text=truncate_text(message_text),
        reply_markup=keyboard
    )

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

@dp.callback_query(F.data == 'top_states')
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

@dp.callback_query(F.data.startswith("important_"))
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

@dp.callback_query(F.data == "back_to_important_list")
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

@dp.callback_query(F.data == 'important_states')
async def show_important_articles(callback: types.CallbackQuery, state: FSMContext):
    print("🔔 Обработчик important_states вызван!")  # Добавить эту строку
    await callback.message.edit_text("📡 Загружаю важные статьи...")




@dp.callback_query(F.data == 'back_main_menu')
async def back_main_menu(callback: types.CallbackQuery):
     await callback.message.edit_text(text='🚀 Выберите нужный раздел в меню ниже:', reply_markup=get_main_menu())

async def main():
    print('Бот запущен!')
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
