from aiogram import Router
from databases.database_constitution import constitution_db
from functions.search_engine import LegalSearchEngine

constitution_search_router = Router()
constitution_engine = LegalSearchEngine(
    router=constitution_search_router,
    db_instance=constitution_db,
    doc_name="Конституция Республики Беларусь",
    collection_name="constitution_articles"
)

constitution_engine.register_handlers(trigger_callback='constitution_search')

@constitution_search_router.startup()
async def on_startup():
    await constitution_engine.get_rag()