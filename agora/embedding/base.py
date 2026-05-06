from abc import ABC, abstractmethod


class WarmingUpError(Exception):
    pass


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def dimension(self) -> int: ...

    def warmup(self):
        pass

    def is_ready(self) -> bool:
        return True
