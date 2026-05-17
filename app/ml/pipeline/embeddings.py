from sentence_transformers import SentenceTransformer
from pathlib import Path

class EmbeddingProvider:
    _instance = None

    @classmethod
    def get(cls) -> SentenceTransformer:
        if cls._instance is None:
            model_name = "paraphrase-multilingual-mpnet-base-v2"
            print(f"[{__name__}] Завантаження embedding моделі: {model_name}")
            cls._instance = SentenceTransformer(model_name)
        return cls._instance

get_encoder = EmbeddingProvider.get