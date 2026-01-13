from aiogram import Router
from databases.database_constitution import constitution_db
from functions.search_engine import LegalSearchEngine

constitution_search_router = Router()

# Инициализируем движок
constitution_engine = LegalSearchEngine(
    router=constitution_search_router,
    db_instance=constitution_db,
    doc_name="Конституция Республики Беларусь",
    collection_name="constitution_articles"
)

# Регистрируем обработчики (привязываем к кнопке 'konstitution_search')
constitution_engine.register_handlers(trigger_callback='konstitution_search')

# Фоновая предзагрузка при старте бота (опционально)
@constitution_search_router.startup()
async def on_startup():
    await constitution_engine.get_rag()