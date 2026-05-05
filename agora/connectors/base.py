import asyncio
from abc import ABC, abstractmethod

_READ_TOOL_PREFIXES = ("list_", "get_", "fetch_", "read_", "search_", "find_",
                       "query_", "describe_", "show_")


class BackendConnector(ABC):
    def __init__(self, name: str, description: str, read_only: bool,
                 transport: str = "stdio", timeout: float = 30.0) -> None:
        self._name = name
        self._description = description
        self._read_only = read_only
        self._transport = transport
        self._timeout = timeout
        self._connected = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def transport(self) -> str:
        return self._transport

    @property
    def timeout(self) -> float:
        return self._timeout

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def list_tools(self) -> list[dict]: ...

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if self._read_only and not tool_name.startswith(_READ_TOOL_PREFIXES):
            raise _ReadOnlyBlockedError(
                f"Backend '{self._name}' is read-only, tool '{tool_name}' blocked. "
                f"Allowed prefixes: {', '.join(_READ_TOOL_PREFIXES)}"
            )
        return await self._call_tool_impl(tool_name, arguments)

    @abstractmethod
    async def _call_tool_impl(self, tool_name: str, arguments: dict) -> dict: ...

    @abstractmethod
    async def health(self) -> bool: ...


class _ReadOnlyBlockedError(Exception):
    pass
