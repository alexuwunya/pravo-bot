from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import logging
import asyncio
from articles_search import news_router
from important_articles import important_news_router
from сonstitution_search import constitution_search_router
from child_rights_search import child_rights_search_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8565646689:AAFFpRkZECKYYIr1laEW6a301algCZ3Qb1Q'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
callback_router = Router()
dp.include_router(news_router)
dp.include_router(important_news_router)
dp.include_router(constitution_search_router)
dp.include_router(child_rights_search_router)

class Operation(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_selection = State()
    waiting_for_article_selection = State()

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💡 Поиск в конституции', callback_data='konstitution_search')],
        [InlineKeyboardButton(text='🔎 Поиск статей', callback_data='state_search')],
        [InlineKeyboardButton(text='⤴ Важные статьи', callback_data='top_states')],
        [InlineKeyboardButton(text='📋 Поиск по актам', callback_data='acts_search')],
        [InlineKeyboardButton(text='🎮 Правовая игра', callback_data='pravo_game')],
        [InlineKeyboardButton(text='🔧 Настройки', callback_data='settings_menu')]
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

acts_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='👶 О правах ребёнка', callback_data='act_child_rights')],
    [InlineKeyboardButton(text='◀️ Назад', callback_data='back_main_menu')]
])

settings_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='💡 Включить уведомления', callback_data='notification_on')],
    [InlineKeyboardButton(text='◀️ Назад', callback_data='back_main_menu')]
])

@dp.callback_query(F.data == 'acts_search')
async def acts_search_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выберите категорию актов:",
        reply_markup=acts_menu
    )
    await callback.answer()

@dp.callback_query(F.data == 'back_main_menu')
async def back_main_menu(callback: types.CallbackQuery):
     await callback.message.edit_text(text='🚀 Выберите нужный раздел в меню ниже:', reply_markup=get_main_menu())

@dp.callback_query(F.data == 'settings_menu')
async def back_main_menu(callback: types.CallbackQuery):
     await callback.message.edit_text(text='🚀 Выберите нужную функцию:', reply_markup=settings_menu)

async def main():
    print('Бот запущен!')
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
