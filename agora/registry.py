from agora.config import BackendConfig
from agora.connectors.base import BackendConnector
from agora.connectors.http import HttpConnector
from agora.connectors.stdio import StdioConnector


class BackendRegistry:
    def __init__(self):
        self._configs: dict[str, BackendConfig] = {}
        self._connectors: dict[str, BackendConnector] = {}

    def register(self, config: BackendConfig) -> None:
        self._configs[config.name] = config

    def get_connector(self, name: str) -> BackendConnector | None:
        connector = self._connectors.get(name)
        if connector is not None:
            return connector
        config = self._configs.get(name)
        if config is None:
            return None
        connector = self._build_connector(config)
        self._connectors[name] = connector
        return connector

    def _build_connector(self, config: BackendConfig) -> BackendConnector:
        timeout = config.timeout_seconds or 30.0
        if config.transport == "stdio":
            cmd = config.command or []
            if not cmd:
                raise ValueError(f"STDIO backend '{config.name}' requires a 'command' in config")
            return StdioConnector(
                name=config.name,
                description=config.description,
                read_only=config.read_only,
                command=cmd,
                env=config.env,
                timeout=timeout,
            )
        if config.transport == "http":
            if not config.url:
                raise ValueError(f"HTTP backend '{config.name}' requires a 'url' field in config")
            return HttpConnector(
                name=config.name,
                description=config.description,
                read_only=config.read_only,
                url=config.url,
                timeout=timeout,
            )
        raise ValueError(f"Unsupported transport '{config.transport}' for backend '{config.name}'")

    def list_backends(self) -> list[BackendConfig]:
        return list(self._configs.values())

    def is_connected(self, name: str) -> bool:
        connector = self._connectors.get(name)
        return connector is not None and connector.is_connected

    def list_connected(self) -> list[str]:
        return [name for name, c in self._connectors.items() if c.is_connected]

    async def disconnect_all(self) -> None:
        for connector in self._connectors.values():
            if connector.is_connected:
                await connector.disconnect()
        self._connectors.clear()
