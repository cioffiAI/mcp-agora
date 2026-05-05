import pytest

from agora.connectors.base import _ReadOnlyBlockedError
from agora.connectors.http import HttpConnector
from agora.connectors.stdio import StdioConnector


def test_connector_properties():
    c = StdioConnector(
        name="test",
        description="Test backend",
        read_only=True,
        command=["echo", "hello"],
    )
    assert c.name == "test"
    assert c.description == "Test backend"
    assert c.read_only is True
    assert c.transport == "stdio"
    assert c.is_connected is False
    assert c.timeout == 30.0


def test_connector_default_read_only():
    c = StdioConnector(
        name="test",
        description="Test backend",
        read_only=False,
        command=["echo", "hello"],
    )
    assert c.read_only is False


def test_connector_custom_timeout():
    c = StdioConnector(
        name="test",
        description="Test",
        read_only=False,
        command=["echo", "hello"],
        timeout=10.0,
    )
    assert c.timeout == 10.0


def test_http_connector_properties():
    c = HttpConnector(
        name="api",
        description="HTTP API backend",
        read_only=True,
        url="http://localhost:8080",
        timeout=10.0,
    )
    assert c.name == "api"
    assert c.description == "HTTP API backend"
    assert c.transport == "http"
    assert c.read_only is True
    assert c.timeout == 10.0
    assert c.is_connected is False


@pytest.mark.asyncio
async def test_health_before_connect():
    c = StdioConnector(
        name="test",
        description="Test backend",
        read_only=False,
        command=["echo", "hello"],
    )
    healthy = await c.health()
    assert healthy is False


@pytest.mark.asyncio
async def test_disconnect_not_connected():
    c = StdioConnector(
        name="test",
        description="Test backend",
        read_only=False,
        command=["echo", "hello"],
    )
    await c.disconnect()


@pytest.mark.asyncio
async def test_read_only_blocks_write_tools():
    c = StdioConnector(
        name="test",
        description="Test",
        read_only=True,
        command=["echo", "hello"],
    )
    with pytest.raises(_ReadOnlyBlockedError) as exc:
        await c.call_tool("create_issue", {"title": "bug"})
    assert "read-only" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_read_only_blocks_write_tool_no_prefix():
    c = StdioConnector(
        name="test",
        description="Test",
        read_only=True,
        command=["echo", "hello"],
    )
    with pytest.raises(_ReadOnlyBlockedError):
        await c.call_tool("delete_repo", {"name": "foo"})


@pytest.mark.asyncio
async def test_read_only_allows_read_prefixes():
    """Read-prefixed tools pass the read_only check (connect may still fail)."""
    allowed_tools = [
        "list_items",
        "get_user",
        "fetch_data",
        "read_file",
        "search_code",
        "find_issues",
        "query_data",
        "describe_schema",
        "show_config",
    ]
    for tool in allowed_tools:
        c = StdioConnector(
            name="test",
            description="Test",
            read_only=True,
            command=["echo", "hello"],
        )
        # Should NOT raise _ReadOnlyBlockedError — the check passes
        # It WILL fail at connect because echo exits, but that's not our concern
        try:
            await c.call_tool(tool, {})
        except _ReadOnlyBlockedError:
            pytest.fail(f"Tool '{tool}' was wrongly blocked (should be allowed)")
        except Exception:
            pass  # connection error is expected


# Full integration test (connect + echo call) is done manually:
#   uv run -q python -c "
#   import anyio, sys
#   from pathlib import Path
#   from agora.connectors.stdio import StdioConnector
#   async def test():
#       c = StdioConnector(name='echo', description='', read_only=True,
#           command=[sys.executable, str(Path('tests/_echo_server.py').resolve())])
#       await c.connect()
#       r = await c.call_tool('echo', {'text': 'hi'})
#       print(r)
#       await c.disconnect()
#   anyio.run(test)
#   "
