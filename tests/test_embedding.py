from agora.embedding.sentence import SentenceTransformerProvider


def test_dimension():
    provider = SentenceTransformerProvider()
    dim = provider.dimension()
    assert dim == 384, f"Expected 384, got {dim}"


def test_embed_returns_list_of_floats():
    provider = SentenceTransformerProvider()
    vectors = provider.embed(["test sentence"])
    assert isinstance(vectors, list)
    assert len(vectors) == 1
    assert isinstance(vectors[0], list)
    assert all(isinstance(v, float) for v in vectors[0])
    assert len(vectors[0]) == 384


def test_document_retrieval_order():
    provider = SentenceTransformerProvider()
    docs = [
        "PostgreSQL BRIN indexes are useful for very large tables",
        "SQLite is a lightweight embedded database",
    ]
    vectors = provider.embed(docs)
    import numpy as np

    def cosine_sim(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    query_vec = provider.embed(["large PostgreSQL tables index"])[0]
    sim_a = cosine_sim(query_vec, vectors[0])
    sim_b = cosine_sim(query_vec, vectors[1])
    assert sim_a > sim_b, f"Expected doc_a ({sim_a}) to be more similar than doc_b ({sim_b})"
