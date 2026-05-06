import gc
import tempfile

from agora.memory.vector_store import VectorStore

try:
    from agora.embedding.sentence import SentenceTransformerProvider

    HAS_EMBEDDING = True
except Exception:
    HAS_EMBEDDING = False


def _cleanup(vs):
    del vs
    gc.collect()


def test_add_and_query():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        vs = VectorStore(path=tmp)
        ids = vs.add(texts=["PostgreSQL BRIN indexes are useful for very large tables"])
        assert len(ids) == 1
        assert vs.count() == 1
        _cleanup(vs)


def test_query_returns_results():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        vs = VectorStore(path=tmp)
        vs.add(texts=["PostgreSQL BRIN indexes are useful"])
        results = vs.query(query_texts=["large PostgreSQL tables"], n_results=5)
        assert len(results) >= 1
        assert "id" in results[0]
        assert "text" in results[0]
        assert "score" in results[0]
        _cleanup(vs)


def test_delete():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        vs = VectorStore(path=tmp)
        ids = vs.add(texts=["test document"])
        assert vs.count() == 1
        vs.delete(ids=ids)
        assert vs.count() == 0
        _cleanup(vs)


def test_multiple_documents():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        vs = VectorStore(path=tmp)
        vs.add(texts=["doc aaa one", "doc bbb two"])
        assert vs.count() == 2
        _cleanup(vs)


def test_integration_save_then_query():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        embedding = None
        if HAS_EMBEDDING:
            embedding = SentenceTransformerProvider()
        vs = VectorStore(path=tmp, embedding_provider=embedding)
        vs.add(texts=["Agora is an MCP server for persistent memory"])
        results = vs.query(query_texts=["MCP memory server"], n_results=5)
        assert len(results) >= 1
        assert "MCP" in results[0]["text"] or "agora" in results[0]["text"].lower()
        _cleanup(vs)
