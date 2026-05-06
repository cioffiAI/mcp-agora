import threading
from pathlib import Path

from agora.embedding.base import EmbeddingProvider, WarmingUpError

_MODEL_NAME = "all-MiniLM-L6-v2"
_CACHE_DIR = Path.home() / ".cache" / "agora" / "models"


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str = _MODEL_NAME):
        self._model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def _load(self) -> bool:
        if self._model is not None:
            return True
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return False
        try:
            if self._model is not None:
                return True
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name,
                cache_folder=str(_CACHE_DIR),
            )
            self._ready.set()
            return True
        finally:
            self._lock.release()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._ready.is_set() and not self._load():
            raise WarmingUpError("Embedding model is loading, please retry in a moment")
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()

    def dimension(self) -> int:
        if not self._ready.is_set() and not self._load():
            raise WarmingUpError("Embedding model is loading, please retry in a moment")
        return self._model.get_embedding_dimension()

    def warmup(self):
        self._load()

    def is_ready(self) -> bool:
        return self._ready.is_set()
