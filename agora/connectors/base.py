from abc import ABC, abstractmethod


class BackendConnector(ABC):
    def __init__(self, name: str, description: str, read_only: bool, transport: str = "stdio") -> None:
        self._name = name
        self._description = description
        self._read_only = read_only
        self._transport = transport
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

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def list_tools(self) -> list[dict]: ...

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict) -> dict: ...

    @abstractmethod
    async def health(self) -> bool: ...
