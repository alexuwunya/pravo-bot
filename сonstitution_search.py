from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import requests
from bs4 import BeautifulSoup
import logging
import re
from database import constitution_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()

constitution_search_router = Router()

@constitution_search_router.startup()
async def on_startup():
    """Автоматически загружает Конституцию в БД при старте, если она еще не загружена"""
    if not constitution_db.is_constitution_loaded():
        logger.info("Конституция не найдена в БД. Запускаю первоначальную загрузку...")
        result = await parse_and_save_constitution()
        if result['success']:
            logger.info("Конституция успешно загружена в БД при старте")
        else:
            logger.error(f"Ошибка загрузки Конституции при старте: {result['error']}")

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

@constitution_search_router.callback_query(F.data == 'konstitution_search')
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

@constitution_search_router.message(Operation.waiting_for_keyword)
async def process_keyword(message: types.Message, state: FSMContext):
    keyword = message.text.strip()
    
    if not keyword:
        await message.answer("Пожалуйста, введите ключевое слово для поиска.")
        return
    
    # Проверяем, загружена ли Конституция в БД
    if not constitution_db.is_constitution_loaded():
        await message.answer("🔄 База данных Конституции загружается...")
        
        # Парсим и сохраняем Конституцию
        result = await parse_and_save_constitution()
        if not result['success']:
            await message.answer(
                f"❌ Ошибка загрузки Конституции: {result['error']}",
                reply_markup=get_back_button()
            )
            await state.clear()
            return
    
    await message.answer("🔍 Ищу информацию в базе данных...")
    
    # Ищем в базе данных
    sentences_data = find_sentences_with_keyword_in_db(keyword)
    
    if not sentences_data:
        await message.answer(
            f"❌ Предложений с ключевым словом '{keyword}' не найдено в Конституции",
            reply_markup=get_back_button()
        )
        await state.clear()
        return
    
    # Сохраняем данные в состоянии
    await state.update_data({
        'sentences_data': sentences_data,
        'keyword': keyword,
        'search_method': 'database'
    })
    
    # Показываем найденные предложения для выбора
    keyboard = create_sentences_keyboard(sentences_data)
    
    message_text = f"🔍 Найдено {len(sentences_data)} предложений с ключевым словом '{keyword}':\n\nВыберите предложение для просмотра контекста:"
    
    await message.answer(
        truncate_text(message_text),
        reply_markup=keyboard
    )
    
    await state.set_state(Operation.waiting_for_selection)

@constitution_search_router.callback_query(Operation.waiting_for_selection, F.data.startswith("sentence_"))
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
@constitution_search_router.callback_query(Operation.waiting_for_selection, F.data.startswith("context_prev_"))
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
@constitution_search_router.callback_query(Operation.waiting_for_selection, F.data.startswith("context_next_"))
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

@constitution_search_router.callback_query(Operation.waiting_for_selection, F.data == "back_to_search")
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
@constitution_search_router.callback_query(Operation.waiting_for_selection, F.data == "back_to_sentences_list")
async def back_to_sentences_list(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sentences_data = data['sentences_data']
    keyword = data['keyword']
    
    keyboard = create_sentences_keyboard(sentences_data)  # Убрал второй аргумент keyword
    
    message_text = f"🔍 Найдено {len(sentences_data)} предложений с ключевым словом '{keyword}':\n\nВыберите предложение для просмотра контекста:"
    
    await callback.message.edit_text(
        text=truncate_text(message_text),
        reply_markup=keyboard
    )
def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Назад', callback_data='back_main_menu')]
    ])

@constitution_search_router.callback_query(F.data == "init_constitution_db")
async def init_constitution_db(callback: types.CallbackQuery):
    await callback.message.answer("🔄 Загружаю Конституцию в базу данных...")
    
    result = await parse_and_save_constitution()
    
    if result['success']:
        await callback.message.answer("✅ Конституция успешно сохранена в базу данных!")
    else:
        await callback.message.answer(f"❌ Ошибка: {result['error']}")

@constitution_search_router.message(Operation.waiting_for_keyword)
async def process_keyword_from_db(message: types.Message, state: FSMContext):
    """Альтернативная функция поиска через базу данных"""
    keyword = message.text.strip()
    
    if not keyword:
        await message.answer("Пожалуйста, введите ключевое слово для поиска.")
        return
    
    await message.answer("🔍 Ищу информацию в базе данных...")
    
    # Ищем в базе данных вместо прямого парсинга
    sentences_data = find_sentences_with_keyword_in_db(keyword)
    
    if not sentences_data:
        await message.answer(
            f"❌ Предложений с ключевым словом '{keyword}' не найдено в Конституции",
            reply_markup=get_back_button()
        )
        await state.clear()
        return
    
    await state.update_data({
        'sentences_data': sentences_data,
        'keyword': keyword
    })
    
    keyboard = create_sentences_keyboard(sentences_data)
    
    message_text = f"🔍 Найдено {len(sentences_data)} предложений с ключевым словом '{keyword}':\n\nВыберите предложение для просмотра контекста:"
    
    await message.answer(
        truncate_text(message_text),
        reply_markup=keyboard
    )
    
    await state.set_state(Operation.waiting_for_selection)

async def parse_and_save_constitution():
    """Парсит и сохраняет Конституцию в базу данных"""
    result = await parse_etalonline_by_document()
    
    if result['success']:
        constitution_db.save_constitution(result['text'], result['url'])
        return {
            'success': True,
            'message': 'Конституция успешно сохранена в базу данных!'
        }
    else:
        return {
            'success': False,
            'error': result['error']
        }

def find_sentences_with_keyword_in_db(keyword):
    return constitution_db.search_sentences(keyword)

@constitution_search_router.callback_query(F.data == "init_constitution_db")
async def init_constitution_db(callback: types.CallbackQuery):
    await callback.message.answer("🔄 Загружаю Конституцию в базу данных...")
    
    result = await parse_and_save_constitution()
    
    if result['success']:
        info = constitution_db.get_constitution_info()
        if info:
            message = (
                f"✅ Конституция успешно сохранена в базу данных!\n"
                f"📊 Проиндексировано предложений: {info['sentence_count']}\n"
                f"🕐 Обновлено: {info['last_updated']}"
            )
        else:
            message = "✅ Конституция успешно сохранена в базу данных!"
        await callback.message.answer(message)
    else:
        await callback.message.answer(f"❌ Ошибка: {result['error']}")

    await callback.message.answer("🔄 Загружаю Конституцию в базу данных...")
    
    result = await parse_and_save_constitution()
    
    if result['success']:
        await callback.message.answer("✅ Конституция успешно сохранена в базу данных!")
    else:
        await callback.message.answer(f"❌ Ошибка: {result['error']}")