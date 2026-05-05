from agora.config import BackendConfig
from agora.connectors.base import BackendConnector
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
        if config.transport == "stdio":
            return StdioConnector(
                name=config.name,
                description=config.description,
                read_only=config.read_only,
                command=config.command or [],
                env=config.env,
            )
        raise ValueError(f"Unsupported transport '{config.transport}' for backend '{config.name}' (only stdio in Phase 2)")

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
