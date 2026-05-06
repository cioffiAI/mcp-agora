import asyncio
import logging
import os
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agora.connectors.base import BackendConnector


class StdioConnector(BackendConnector):
    def __init__(
        self,
        name: str,
        description: str,
        read_only: bool,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        rate_limit_rps: float = 0.0,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            name,
            description,
            read_only,
            transport="stdio",
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            rate_limit_rps=rate_limit_rps,
            logger=logger,
        )
        self._command = command
        self._env_overrides = env or {}
        self._cwd = cwd
        self._session: ClientSession | None = None
        self._read_stream = None
        self._write_stream = None
        self._exit_stack: AsyncExitStack | None = None

    async def _ensure_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        await self.connect()
        return self._session

    async def connect(self) -> None:
        if self._connected:
            return
        merged_env = {**os.environ, **self._env_overrides} if self._env_overrides else None
        params = StdioServerParameters(
            command=self._command[0],
            args=self._command[1:] if len(self._command) > 1 else [],
            env=merged_env,
            cwd=self._cwd,
        )
        self._exit_stack = AsyncExitStack()
        try:
            async with asyncio.timeout(self._timeout):
                streams = await self._exit_stack.enter_async_context(stdio_client(params))
                self._read_stream, self._write_stream = streams
                self._session = await self._exit_stack.enter_async_context(
                    ClientSession(self._read_stream, self._write_stream)
                )
                await self._session.initialize()
        except TimeoutError:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._log.warning("Timeout connecting to backend '%s' after %.1fs", self._name, self._timeout)
            raise ConnectionError(
                f"Timeout ({self._timeout:.1f}s) connecting to backend '{self._name}'. Is the backend running?"
            )
        except OSError as e:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._log.warning("OS error connecting to backend '%s': %s", self._name, e)
            raise ConnectionError(f"Failed to connect to backend '{self._name}': {e}")
        self._connected = True
        self._log.info("Connected to backend '%s' (transport=stdio)", self._name)

    async def disconnect(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._session = None
        self._read_stream = None
        self._write_stream = None
        if self._connected:
            self._log.info("Disconnected from backend '%s'", self._name)
        self._connected = False

    async def list_tools(self) -> list[dict]:
        session = await self._ensure_session()
        tools_result = await session.list_tools()
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools_result.tools
        ]

    async def _call_tool_impl(self, tool_name: str, arguments: dict) -> dict:
        session = await self._ensure_session()
        result = await session.call_tool(tool_name, arguments)
        content = []
        for item in result.content:
            content.append({"type": item.type, "text": item.text})
        return {
            "content": content,
            "isError": getattr(result, "isError", False),
        }
