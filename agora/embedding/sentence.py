from pathlib import Path

from agora.embedding.base import EmbeddingProvider

_MODEL_NAME = "all-MiniLM-L6-v2"
_CACHE_DIR = Path.home() / ".cache" / "agora" / "models"


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str = _MODEL_NAME):
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self._model_name,
            cache_folder=str(_CACHE_DIR),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()

    def dimension(self) -> int:
        self._load()
        return self._model.get_embedding_dimension()

    def warmup(self):
        self._load()
