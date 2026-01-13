from aiogram import Router
from databases.childrights_db import child_rights_db
from functions.search_engine import LegalSearchEngine

child_rights_search_router = Router()

# Инициализируем движок
child_rights_engine = LegalSearchEngine(
    router=child_rights_search_router,
    db_instance=child_rights_db,
    doc_name="Закон О правах ребенка",
    collection_name="child_rights_law"
)

# Регистрируем обработчики (привязываем к кнопке 'act_child_rights')
child_rights_engine.register_handlers(trigger_callback='act_child_rights')

@child_rights_search_router.startup()
async def on_startup():
    await child_rights_engine.get_rag()