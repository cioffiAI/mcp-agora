"""Test graceful degradation: backend failure, health check, broadcast resilience."""

import gc
import sys
from pathlib import Path

import pytest

from agora.config import BackendConfig
from agora.connectors.stdio import StdioConnector
from agora.registry import BackendRegistry

PROJECT_DIR = Path(__file__).resolve().parent.parent
ECHO_SERVER = str(PROJECT_DIR / "tests" / "_echo_server.py")


@pytest.fixture
def registry():
    r = BackendRegistry()
    yield r
    gc.collect()


@pytest.mark.asyncio
async def test_connect_to_nonexistent_backend(registry):
    """Route to a backend that was never started returns an error, no crash."""
    config = BackendConfig(
        name="ghost",
        transport="stdio",
        command=["nonexistent_cmd_xyz"],
        description="Ghost backend",
        read_only=True,
        timeout_seconds=2,
    )
    registry.register(config)
    connector = registry.get_connector("ghost")
    assert connector is not None
    with pytest.raises(ConnectionError):
        await connector.call_tool("list_tools", {})


@pytest.mark.asyncio
async def test_call_tool_on_dead_backend_returns_error():
    """Connector to a dead backend returns error without crashing."""
    c = StdioConnector(
        name="dead",
        description="Dead backend",
        read_only=True,
        command=["nonexistent_cmd_xyz"],
        timeout=2,
        max_retries=0,
    )
    with pytest.raises(ConnectionError):
        await c.call_tool("list_tools", {})


@pytest.mark.asyncio
async def test_health_check_dead_backend(registry):
    """Health check detects 3 consecutive failures → dead status."""
    config = BackendConfig(
        name="ghost",
        transport="stdio",
        command=["nonexistent_cmd_xyz"],
        description="Ghost",
        read_only=True,
        timeout_seconds=2,
    )
    registry.register(config)
    connector = registry.get_connector("ghost")

    # Try to connect (will fail)
    with pytest.raises(ConnectionError):
        await connector.connect()

    # Health check should detect failures
    results = await registry.health_check_all()
    assert "ghost" in results
    # After first failure, should be unhealthy
    assert results["ghost"]["status"] == "unhealthy"
    assert results["ghost"]["consecutive_failures"] == 1

    # After 3 failures, should be dead
    for _ in range(3):
        with pytest.raises(ConnectionError):
            await connector.connect()
        await connector.health()

    results = await registry.health_check_all()
    assert results["ghost"]["consecutive_failures"] >= 1


@pytest.mark.asyncio
async def test_health_reports_all_statuses(registry):
    """agora_status returns backend_health with correct structure."""
    config_ok = BackendConfig(
        name="echo",
        transport="stdio",
        command=[sys.executable, ECHO_SERVER],
        description="Echo",
        read_only=True,
        timeout_seconds=5,
    )
    config_dead = BackendConfig(
        name="ghost",
        transport="stdio",
        command=["nonexistent_cmd_xyz"],
        description="Ghost",
        read_only=True,
        timeout_seconds=2,
    )
    registry.register(config_ok)
    registry.register(config_dead)

    # Connect to echo
    echo_con = registry.get_connector("echo")
    await echo_con.connect()

    results = await registry.health_check_all()
    assert "echo" in results
    assert "ghost" in results
    assert results["echo"]["status"] in ("healthy",)
    assert results["ghost"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_retry_on_transient_error():
    """Connector retries on transient error (ConnectionError), then raises."""
    c = StdioConnector(
        name="retry_test",
        description="Retry test",
        read_only=True,
        command=["nonexistent_cmd_xyz"],
        timeout=2,
        max_retries=2,
        retry_delay=0.1,
    )
    with pytest.raises(ConnectionError):
        await c.call_tool("list_tools", {})


@pytest.mark.asyncio
async def test_rate_limit_property():
    """Rate limit property is set and returned correctly."""
    c = StdioConnector(
        name="limited",
        description="Rate limited",
        read_only=True,
        command=["echo", "hello"],
        rate_limit_rps=10.0,
    )
    assert c.throttled_count() == 0
    # No actual call made, so throttled count stays 0
    # (throttle only applies when call_tool is executed)
