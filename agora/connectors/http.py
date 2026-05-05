from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agora.connectors.base import BackendConnector


class HttpConnector(BackendConnector):
    def __init__(self, name: str, description: str, read_only: bool,
                 url: str, headers: dict[str, str] | None = None,
                 timeout: float = 30.0) -> None:
        super().__init__(name, description, read_only, transport="http", timeout=timeout)
        self._url = url
        self._headers = headers or {}
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
        self._exit_stack = AsyncExitStack()
        client = streamablehttp_client(
            self._url,
            headers=self._headers,
            timeout=self._timeout,
        )
        transport = await self._exit_stack.enter_async_context(client)
        self._read_stream, self._write_stream, _ = transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(self._read_stream, self._write_stream)
        )
        await self._session.initialize()
        self._connected = True

    async def disconnect(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._session = None
        self._read_stream = None
        self._write_stream = None
        self._connected = False

    async def list_tools(self) -> list[dict]:
        session = await self._ensure_session()
        tools_result = await session.list_tools()
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
            for t in tools_result.tools
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

    async def health(self) -> bool:
        try:
            return self._connected and self._session is not None
        except Exception:
            return False
