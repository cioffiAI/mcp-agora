import tempfile

from agora.db.database import Database


def _fresh_db():
    tmp = tempfile.mkdtemp()
    return Database(path=tmp + "/agora.db")


def test_register_new_agent():
    db = _fresh_db()
    result = db.register_agent("agent-a", agent_type="test")
    assert result["agent"] == "agent-a"
    assert result["new"] is True

    agent = db.get_agent("agent-a")
    assert agent is not None
    assert agent["name"] == "agent-a"
    assert agent["agent_type"] == "test"
    assert agent["sessions_count"] == 1


def test_register_existing_agent():
    db = _fresh_db()
    db.register_agent("agent-a")
    result = db.register_agent("agent-a")
    assert result["new"] is False

    agent = db.get_agent("agent-a")
    assert agent["sessions_count"] == 2


def test_list_agents():
    db = _fresh_db()
    db.register_agent("alpha")
    db.register_agent("beta")
    agents = db.list_agents()
    assert len(agents) == 2
    names = [a["name"] for a in agents]
    assert "alpha" in names
    assert "beta" in names


def test_add_and_get_provenance():
    db = _fresh_db()
    db.register_agent("agent-a")
    db.add_provenance(entry_id="mem_001", source_agent="agent-a", source_session="session-1", confidence=0.8)
    prov = db.get_provenance("mem_001")
    assert prov is not None
    assert prov["source_agent"] == "agent-a"
    assert prov["source_session"] == "session-1"
    assert prov["confidence"] == 0.8


def test_list_provenance_by_agent():
    db = _fresh_db()
    db.register_agent("agent-a")
    db.register_agent("agent-b")
    db.add_provenance("mem_001", "agent-a", "s1")
    db.add_provenance("mem_002", "agent-b", "s2")
    db.add_provenance("mem_003", "agent-a", "s3")
    a_prov = db.list_provenance(agent="agent-a")
    assert len(a_prov) == 2
    all_prov = db.list_provenance()
    assert len(all_prov) == 3


def test_delete_provenance():
    db = _fresh_db()
    db.register_agent("agent-a")
    db.add_provenance("mem_001", "agent-a", "s1")
    db.add_provenance("mem_002", "agent-a", "s2")
    db.delete_provenance(["mem_001"])
    assert db.get_provenance("mem_001") is None
    assert db.get_provenance("mem_002") is not None


def test_delete_provenance_by_agent():
    db = _fresh_db()
    db.register_agent("agent-a")
    db.register_agent("agent-b")
    db.add_provenance("mem_001", "agent-a", "s1")
    db.add_provenance("mem_002", "agent-b", "s2")
    db.delete_provenance_by_agent("agent-a")
    assert db.get_provenance("mem_001") is None
    assert db.get_provenance("mem_002") is not None
