import math

from agora.connectors.base import BackendConnector
from agora.embedding.base import EmbeddingProvider
from agora.registry import BackendRegistry

SEMANTIC_THRESHOLD = 0.5


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class Router:
    def __init__(self, registry: BackendRegistry, embedding_provider: EmbeddingProvider) -> None:
        self._registry = registry
        self._embedding = embedding_provider
        self._backend_embeddings: dict[str, list[float]] = {}
        self._warmed_up = False

    def _warmup(self) -> None:
        if self._warmed_up:
            return
        for backend in self._registry.list_backends():
            if backend.description:
                emb = self._embedding.embed([backend.description])[0]
                self._backend_embeddings[backend.name] = emb
        self._warmed_up = True

    def warmup(self) -> None:
        self._warmup()

    def route(self, target: str) -> tuple[BackendConnector | None, str, float]:
        self._warmup()
        if not target.strip():
            return None, "none", 0.0

        target_stripped = target.strip().lower()

        # 1. Exact name match (case-insensitive)
        for backend in self._registry.list_backends():
            if backend.name.lower() == target_stripped:
                connector = self._registry.get_connector(backend.name)
                if connector is not None:
                    return connector, "exact", 1.0

        # 2. Semantic match
        if not self._backend_embeddings:
            return None, "none", 0.0

        query_emb = self._embedding.embed([target])[0]
        best_name = None
        best_score = 0.0
        for name, emb in self._backend_embeddings.items():
            score = cosine_similarity(query_emb, emb)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score >= SEMANTIC_THRESHOLD and best_name is not None:
            connector = self._registry.get_connector(best_name)
            if connector is not None:
                return connector, "semantic", best_score

        return None, "none", best_score
