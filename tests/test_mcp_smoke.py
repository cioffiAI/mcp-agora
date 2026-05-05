import json
import os
import tempfile
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

PROJECT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="function")
def mcp_env():
    tmp = tempfile.mkdtemp()
    chroma_path = Path(tmp) / "chroma"
    chroma_path.mkdir()
    db_path = Path(tmp) / "agora.db"
    config = {
        "agora": {"name": "Agora", "version": "0.3.0"},
        "storage": {"chroma_path": str(chroma_path), "db_path": str(db_path)},
        "cache": {"l1_max_entries": 100, "l1_ttl_seconds": 60, "l2_max_entries": 100, "l2_ttl_seconds": 3600},
        "embedding": {"provider": "sentence-transformers", "model": "all-MiniLM-L6-v2"},
    }
    config_path = Path(tmp) / "config.yaml"
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return config_path


@pytest.fixture(scope="function")
def server_params(mcp_env):
    return StdioServerParameters(
        command="uv",
        args=["run", "agora"],
        cwd=str(PROJECT_DIR),
        env={**os.environ, "AGORA_CONFIG": str(mcp_env)},
    )


@pytest.mark.asyncio
async def test_mcp_full_smoke(server_params):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- list_tools ---
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            assert "agora_save" in tool_names
            assert "agora_query" in tool_names
            assert "agora_status" in tool_names
            assert "agora_route" in tool_names
            assert "agora_backends" in tool_names
            assert "agora_broadcast" in tool_names
            assert "agora_crossref" in tool_names
            assert "agora_forget" in tool_names

            # --- agora_status (empty) ---
            status = json.loads((await session.call_tool("agora_status", arguments={})).content[0].text)
            assert status["server"] == "Agora"
            assert status["memory_entries"] == 0
            assert "agents" in status
            assert "db_size_bytes" in status

            # --- agora_save ---
            save_result = await session.call_tool(
                "agora_save",
                arguments={"content": "PostgreSQL BRIN indexes are useful for very large tables with correlated data",
                           "tags": ["postgres", "sql", "performance"]},
            )
            saved = json.loads(save_result.content[0].text)
            assert saved["saved"] is True
            assert saved["id"].startswith("mem_")

            # --- agora_query (same session, should find the saved entry) ---
            query_result = await session.call_tool(
                "agora_query",
                arguments={"query": "PostgreSQL indexing performance", "top_k": 5},
            )
            data = json.loads(query_result.content[0].text)
            assert len(data["results"]) >= 1
            assert "BRIN" in data["results"][0]["text"]
            assert data["cached"] is False

            # --- cache hit on repeated query ---
            second = await session.call_tool(
                "agora_query",
                arguments={"query": "PostgreSQL indexing performance", "top_k": 5},
            )
            assert json.loads(second.content[0].text)["cached"] is True

            # --- agora_status (now with 1 entry) ---
            status2 = json.loads((await session.call_tool("agora_status", arguments={})).content[0].text)
            assert status2["memory_entries"] == 1
            assert status2["cache_stats"]["l1"]["hit_count"] >= 1
            assert "l2" in status2["cache_stats"]
            assert status2["agents"]["total"] >= 1

            # --- save clears cache, so next query is fresh ---
            await session.call_tool("agora_save", arguments={"content": "Redis Streams support consumer groups"})
            after_save = await session.call_tool(
                "agora_query",
                arguments={"query": "PostgreSQL indexing performance", "top_k": 5},
            )
            assert json.loads(after_save.content[0].text)["cached"] is False

            # --- agora_crossref by query ---
            crossref_q = await session.call_tool(
                "agora_crossref",
                arguments={"query": "PostgreSQL performance", "top_k": 3},
            )
            cr_q = json.loads(crossref_q.content[0].text)
            assert cr_q["mode"] == "query"
            assert cr_q["total_entries"] >= 1
            assert "cross_agent_groups" in cr_q

            # --- agora_crossref by entry_id ---
            crossref_id = await session.call_tool(
                "agora_crossref",
                arguments={"entry_id": saved["id"], "top_k": 3},
            )
            cr_id = json.loads(crossref_id.content[0].text)
            assert cr_id["mode"] == "entry_id"
            assert cr_id["source_entry_id"] == saved["id"]

            # --- agora_forget with dry_run ---
            forget_dry = await session.call_tool(
                "agora_forget",
                arguments={"entry_ids": [saved["id"]], "dry_run": True},
            )
            fd = json.loads(forget_dry.content[0].text)
            assert fd["dry_run"] is True
            assert fd["forgotten"] == 0

            # --- agora_forget real ---
            forget_real = await session.call_tool(
                "agora_forget",
                arguments={"entry_ids": [saved["id"]]},
            )
            fr = json.loads(forget_real.content[0].text)
            assert fr["forgotten"] >= 1

            # Verify status reflects deletion
            status3 = json.loads((await session.call_tool("agora_status", arguments={})).content[0].text)
            assert status3["memory_entries"] == 1  # Redis entry still there


@pytest.mark.asyncio
async def test_mcp_multiple_entries(server_params):
    entries = [
        "Python async/await with asyncio enables concurrent I/O operations",
        "PostgreSQL CTEs are useful for recursive queries and data transformation",
        "Redis sorted sets are efficient for leaderboards and ranked data",
        "Docker multi-stage builds reduce final image size significantly",
        "FastAPI dependency injection simplifies request validation and auth",
    ]
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            saved_ids = []
            for entry in entries:
                result = await session.call_tool("agora_save", arguments={"content": entry})
                data = json.loads(result.content[0].text)
                assert data["saved"] is True
                saved_ids.append(data["id"])

            result = await session.call_tool(
                "agora_query",
                arguments={"query": "database indexing and performance", "top_k": 3},
            )
            data = json.loads(result.content[0].text)
            assert len(data["results"]) >= 1
            texts = [r["text"] for r in data["results"]]
            has_db_related = any(
                "PostgreSQL" in t or "Redis" in t for t in texts
            )
            assert has_db_related, f"No relevant results among: {texts}"


@pytest.mark.asyncio
async def test_mcp_stress_save_and_query(server_params):
    """Stress test: save 15 entries across diverse topics, then query and verify."""
    entries = [
        ("Kubernetes pods are the smallest deployable units in a cluster", ["kubernetes", "devops"]),
        ("Terraform state files track infrastructure resources and dependencies", ["terraform", "iac"]),
        ("GraphQL allows clients to request exactly the data they need", ["graphql", "api"]),
        ("JWT tokens contain a header, payload, and signature for stateless auth", ["jwt", "auth", "security"]),
        ("CSS Grid provides a two-dimensional layout system for web pages", ["css", "frontend"]),
        ("gRPC uses Protocol Buffers for efficient binary serialization", ["grpc", "rpc", "performance"]),
        ("Linux cgroups limit and isolate resource usage of process groups", ["linux", "containers"]),
        ("SQL window functions compute values across rows without collapsing results", ["sql", "database"]),
        ("Prometheus scrapes metrics from HTTP endpoints and stores time-series data", ["prometheus", "monitoring"]),
        ("React hooks let you use state and lifecycle features in function components", ["react", "frontend", "hooks"]),
        ("Apache Kafka uses partitioned logs for high-throughput message streaming", ["kafka", "streaming"]),
        ("Nginx reverse proxy handles request routing, SSL termination, and caching", ["nginx", "infrastructure"]),
        ("TypeScript generics enable type-safe reusable functions and components", ["typescript", "programming"]),
        ("MongoDB aggregation pipeline processes documents through sequential stages", ["mongodb", "database"]),
        ("OAuth 2.0 authorization code flow is the most secure grant type for web apps", ["oauth", "auth", "security"]),
    ]

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Save all 15 entries
            saved_ids = []
            for content, tags in entries:
                result = await session.call_tool(
                    "agora_save",
                    arguments={"content": content, "tags": tags},
                )
                data = json.loads(result.content[0].text)
                assert data["saved"] is True
                assert data["id"].startswith("mem_")
                saved_ids.append(data["id"])

            assert len(saved_ids) == 15
            assert len(set(saved_ids)) == 15  # all unique

            # Query 1: database-related
            q1 = await session.call_tool(
                "agora_query",
                arguments={"query": "database querying and aggregation", "top_k": 5},
            )
            d1 = json.loads(q1.content[0].text)
            assert d1["cached"] is False
            assert len(d1["results"]) >= 1
            texts1 = [r["text"] for r in d1["results"]]
            assert any("SQL" in t or "MongoDB" in t for t in texts1), f"Missing DB results: {texts1}"

            # Query 2: frontend/web
            q2 = await session.call_tool(
                "agora_query",
                arguments={"query": "web frontend development frameworks", "top_k": 5},
            )
            d2 = json.loads(q2.content[0].text)
            assert d2["cached"] is False
            texts2 = [r["text"] for r in d2["results"]]
            assert any("React" in t or "CSS" in t for t in texts2), f"Missing frontend results: {texts2}"

            # Query 3: auth/security
            q3 = await session.call_tool(
                "agora_query",
                arguments={"query": "authentication and security protocols", "top_k": 5},
            )
            d3 = json.loads(q3.content[0].text)
            assert d3["cached"] is False
            texts3 = [r["text"] for r in d3["results"]]
            assert any("JWT" in t or "OAuth" in t for t in texts3), f"Missing auth results: {texts3}"

            # Query 4: infrastructure/containers
            q4 = await session.call_tool(
                "agora_query",
                arguments={"query": "container orchestration and infrastructure", "top_k": 5},
            )
            d4 = json.loads(q4.content[0].text)
            assert d4["cached"] is False
            texts4 = [r["text"] for r in d4["results"]]
            assert any("Kubernetes" in t or "Terraform" in t for t in texts4), f"Missing infra results: {texts4}"

            # Cache hit: repeat query 1
            q1_repeat = await session.call_tool(
                "agora_query",
                arguments={"query": "database querying and aggregation", "top_k": 5},
            )
            d1r = json.loads(q1_repeat.content[0].text)
            assert d1r["cached"] is True
            assert d1r["results"] == d1["results"]

            # Cache hit: repeat query 3
            q3_repeat = await session.call_tool(
                "agora_query",
                arguments={"query": "authentication and security protocols", "top_k": 5},
            )
            d3r = json.loads(q3_repeat.content[0].text)
            assert d3r["cached"] is True
            assert d3r["results"] == d3["results"]

            # Status check
            status = json.loads((await session.call_tool("agora_status", arguments={})).content[0].text)
            assert status["memory_entries"] == 15
            assert status["cache_stats"]["l1"]["hit_count"] >= 2

            # Save clears cache — verify by repeating a previously cached query
            await session.call_tool(
                "agora_save",
                arguments={"content": "WebAssembly enables near-native performance in browsers", "tags": ["wasm", "performance"]},
            )
            q1_after_save = await session.call_tool(
                "agora_query",
                arguments={"query": "database querying and aggregation", "top_k": 5},
            )
            d1_after = json.loads(q1_after_save.content[0].text)
            assert d1_after["cached"] is False

            # Verify the new entry is found
            q_wasm = await session.call_tool(
                "agora_query",
                arguments={"query": "browser performance webassembly", "top_k": 3},
            )
            d_wasm = json.loads(q_wasm.content[0].text)
            assert any("WebAssembly" in r["text"] for r in d_wasm["results"]), "New entry not found"


@pytest.fixture(scope="function")
def mcp_env_with_backends():
    tmp = tempfile.mkdtemp()
    chroma_path = Path(tmp) / "chroma"
    chroma_path.mkdir()
    db_path = Path(tmp) / "agora.db"
    config = {
        "agora": {"name": "Agora", "version": "0.3.0"},
        "storage": {"chroma_path": str(chroma_path), "db_path": str(db_path)},
        "cache": {"l1_max_entries": 100, "l1_ttl_seconds": 60, "l2_max_entries": 100, "l2_ttl_seconds": 3600},
        "embedding": {"provider": "sentence-transformers", "model": "all-MiniLM-L6-v2"},
        "backends": [
            {
                "name": "echo",
                "transport": "stdio",
                "command": ["python", "-c", "pass"],
                "description": "Echo server: returns text back as-is",
                "read_only": True,
            },
        ],
    }
    config_path = Path(tmp) / "config.yaml"
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return config_path


@pytest.fixture(scope="function")
def server_params_with_backends(mcp_env_with_backends):
    return StdioServerParameters(
        command="uv",
        args=["run", "agora"],
        cwd=str(PROJECT_DIR),
        env={**os.environ, "AGORA_CONFIG": str(mcp_env_with_backends)},
    )


@pytest.mark.asyncio
async def test_mcp_routing(server_params_with_backends):
    """Test routing tools: agora_route (no-match), agora_backends, agora_status."""
    async with stdio_client(server_params_with_backends) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            assert "agora_route" in tool_names
            assert "agora_backends" in tool_names
            assert "agora_broadcast" in tool_names

            # --- agora_backends lists configured backend (not connected) ---
            backends = json.loads((await session.call_tool("agora_backends", arguments={})).content[0].text)
            assert len(backends["backends"]) == 1
            assert backends["backends"][0]["name"] == "echo"
            assert backends["backends"][0]["connected"] is False
            assert backends["backends"][0]["read_only"] is True

            # --- agora_route with no match returns error ---
            no_match = await session.call_tool(
                "agora_route",
                arguments={"target": "nonexistent", "tool": "echo", "arguments": {}},
            )
            err = json.loads(no_match.content[0].text)
            assert "error" in err
            assert "No backend" in err["error"]

            # --- agora_route with read_only backend + write tool → blocked ---
            blocked = await session.call_tool(
                "agora_route",
                arguments={"target": "echo", "tool": "create_issue", "arguments": {}},
            )
            blocked_data = json.loads(blocked.content[0].text)
            assert blocked_data.get("blocked") is True
            assert "read-only" in blocked_data.get("error", "").lower()

            # --- agora_broadcast returns results for all configured backends ---
            broadcast = await session.call_tool(
                "agora_broadcast",
                arguments={"tool": "echo", "arguments": {}},
            )
            broadcast_data = json.loads(broadcast.content[0].text)
            assert broadcast_data["tool"] == "echo"
            assert "results" in broadcast_data
            assert "echo" in broadcast_data["results"]

            # --- agora_status includes backends section ---
            status = json.loads((await session.call_tool("agora_status", arguments={})).content[0].text)
            assert "backends" in status
            assert status["backends"]["total"] == 1
            assert status["backends"]["connected"] == 0
