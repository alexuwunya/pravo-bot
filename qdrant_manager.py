import os
from qdrant_client import QdrantClient


class QdrantManager:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QdrantManager, cls).__new__(cls)
            cls._initialize_client()
        return cls._instance

    @classmethod
    def _initialize_client(cls):
        """Инициализирует клиент Qdrant"""
        qdrant_path = "./qdrant_data"
        if not os.path.exists(qdrant_path):
            os.makedirs(qdrant_path)
        cls._client = QdrantClient(path=qdrant_path)

    @classmethod
    def get_client(cls):
        """Возвращает общий клиент Qdrant"""
        if cls._client is None:
            cls._initialize_client()
        return cls._client


# Глобальный экземпляр менеджера
qdrant_manager = QdrantManager()