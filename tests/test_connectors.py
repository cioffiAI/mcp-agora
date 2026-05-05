import pytest

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


def test_connector_default_read_only():
    c = StdioConnector(
        name="test",
        description="Test backend",
        read_only=False,
        command=["echo", "hello"],
    )
    assert c.read_only is False


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
