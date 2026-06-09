import threading

from agora.embedding.base import EmbeddingProvider, WarmingUpError

_MODEL_NAME = "all-MiniLM-L6-v2"


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str = _MODEL_NAME):
        self._model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def _build_model(self):
        """Load the model offline-first, downloading it once only if it is not
        already in the local HuggingFace cache.

        Forcing ``local_files_only=True`` unconditionally raises ``OSError`` on any
        machine where the model was never cached. That exception used to propagate
        out of ``create_server()`` and kill the process before ``mcp.run()`` — the
        root cause of the "server never starts / Not connected" bug. Offline-first
        keeps the fast, no-network path for normal runs while self-healing on a
        fresh machine.
        """
        from sentence_transformers import SentenceTransformer

        try:
            return SentenceTransformer(self._model_name, local_files_only=True)
        except Exception:
            # Model not in local cache yet → download it once. Subsequent runs are
            # served from the cache via the offline path above.
            return SentenceTransformer(self._model_name, local_files_only=False)

    def _load(self) -> bool:
        if self._model is not None:
            return True
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return False
        try:
            if self._model is not None:
                return True
            self._model = self._build_model()
            self._ready.set()
            return True
        finally:
            self._lock.release()

    def _ensure_ready(self):
        if self._ready.is_set():
            return
        if self._load():
            return
        if self._ready.wait(timeout=60.0):
            return
        raise WarmingUpError("Embedding model is still loading after 60s, please retry")

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure_ready()
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()

    def dimension(self) -> int:
        self._ensure_ready()
        return self._model.get_embedding_dimension()

    def warmup(self):
        self._load()

    def is_ready(self) -> bool:
        return self._ready.is_set()

    def ensure_ready(self):
        self._ensure_ready()
