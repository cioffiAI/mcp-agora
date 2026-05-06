from pathlib import Path

import chromadb
from chromadb.config import Settings

from agora.embedding.base import EmbeddingProvider

_DEFAULT_PATH = Path.home() / ".agora" / "chroma"
_COLLECTION_KNOWLEDGE = "knowledge"


class VectorStore:
    def __init__(self, path: str | None = None, embedding_provider: EmbeddingProvider | None = None):
        self._path = Path(path or _DEFAULT_PATH).expanduser()
        self._path.mkdir(parents=True, exist_ok=True)
        self._embedding_provider = embedding_provider
        self._client = chromadb.PersistentClient(
            path=str(self._path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._knowledge = self._client.get_or_create_collection(
            name=_COLLECTION_KNOWLEDGE,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def knowledge_collection(self):
        return self._knowledge

    def add(self, texts: list[str], metadata: list[dict] | None = None, ids: list[str] | None = None):
        if ids is None:
            import uuid

            ids = [str(uuid.uuid4()) for _ in texts]
        embeddings = None
        if self._embedding_provider:
            embeddings = self._embedding_provider.embed(texts)
        kwargs = {
            "documents": texts,
            "ids": ids,
            "embeddings": embeddings,
        }
        if metadata is not None:
            kwargs["metadatas"] = metadata
        self._knowledge.add(**{k: v for k, v in kwargs.items() if v is not None})
        return ids

    def query(self, query_texts: list[str], n_results: int = 5) -> list[dict]:
        query_embeddings = None
        if self._embedding_provider:
            query_embeddings = self._embedding_provider.embed(query_texts)
        results = self._knowledge.query(
            query_texts=query_texts,
            query_embeddings=query_embeddings,
            n_results=n_results,
        )
        out = []
        for i in range(len(results["ids"][0])):
            out.append(
                {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "score": results["distances"][0][i] if results["distances"] else 0.0,
                }
            )
        return out

    def delete(self, ids: list[str]):
        self._knowledge.delete(ids=ids)

    def count(self) -> int:
        return self._knowledge.count()
