from agora.config import BackendConfig
from agora.registry import BackendRegistry
from agora.routing.router import Router, cosine_similarity


class MockEmbedding:
    def warmup(self):
        pass

    def dimension(self) -> int:
        return 4

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                sum(ord(c) for c in texts[0][:20]) / 1000,
                0.5,
                0.3,
                0.1,
            ]
        ]


def test_cosine_similarity_identical():
    v = [1.0, 2.0, 3.0]
    assert cosine_similarity(v, v) == 1.0


def test_cosine_similarity_orthogonal():
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0


def test_cosine_similarity_zero_vector():
    assert cosine_similarity([0, 0, 0], [1, 0, 0]) == 0.0


def test_exact_name_match():
    registry = BackendRegistry()
    registry.register(
        BackendConfig(
            name="github",
            description="GitHub API: issues, PRs, repos",
            command=["npx", "server-github"],
            read_only=False,
        )
    )
    registry.register(
        BackendConfig(
            name="playwright",
            description="Browser automation",
            command=["npx", "playwright"],
            read_only=False,
        )
    )
    router = Router(registry, MockEmbedding())
    router.warmup()

    connector, method, score = router.route("github")
    assert connector is not None
    assert connector.name == "github"
    assert method == "exact"
    assert score == 1.0


def test_case_insensitive_exact():
    registry = BackendRegistry()
    registry.register(
        BackendConfig(
            name="GitHub",
            description="GitHub API",
            command=["npx", "server-github"],
            read_only=False,
        )
    )
    router = Router(registry, MockEmbedding())
    router.warmup()

    connector, method, score = router.route("github")
    assert connector is not None
    assert method == "exact"


def test_semantic_match():
    registry = BackendRegistry()
    registry.register(
        BackendConfig(
            name="github",
            description="GitHub API: issues, PRs, repos, code search, commits",
            command=["npx", "server-github"],
            read_only=False,
        )
    )
    registry.register(
        BackendConfig(
            name="playwright",
            description="Browser automation: navigate, click, screenshot",
            command=["npx", "playwright"],
            read_only=False,
        )
    )
    router = Router(registry, MockEmbedding())
    router.warmup()

    connector, method, score = router.route("search code on GitHub")
    assert connector is not None
    assert method == "semantic"
    assert score >= 0.5


def test_no_match():
    registry = BackendRegistry()
    registry.register(
        BackendConfig(
            name="github",
            description="GitHub API",
            command=["npx", "server-github"],
            read_only=False,
        )
    )
    router = Router(registry, MockEmbedding())
    router.warmup()

    connector, method, score = router.route("")
    assert connector is None
    assert method == "none"


def test_empty_registry():
    registry = BackendRegistry()
    router = Router(registry, MockEmbedding())
    router.warmup()

    connector, method, score = router.route("anything")
    assert connector is None
    assert method == "none"


def test_warmup_populates_embeddings():
    registry = BackendRegistry()
    registry.register(
        BackendConfig(
            name="github",
            description="GitHub API",
            command=["npx", "server-github"],
            read_only=False,
        )
    )
    router = Router(registry, MockEmbedding())
    router.warmup()
    assert len(router._backend_embeddings) == 1
    assert "github" in router._backend_embeddings
