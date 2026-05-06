import logging
import time

from agora.config import BackendConfig
from agora.connectors.base import BackendConnector
from agora.connectors.http import HttpConnector
from agora.connectors.stdio import StdioConnector


class BackendRegistry:
    def __init__(self, logger: logging.Logger | None = None):
        self._configs: dict[str, BackendConfig] = {}
        self._connectors: dict[str, BackendConnector] = {}
        self._health_cache: dict[str, dict] = {}
        self._log = logger or logging.getLogger("agora.registry")

    def register(self, config: BackendConfig) -> None:
        self._configs[config.name] = config
        self._log.debug("Backend registered: name=%s transport=%s", config.name, config.transport)

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
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                rate_limit_rps=config.rate_limit_rps,
                logger=self._log,
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
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                rate_limit_rps=config.rate_limit_rps,
                logger=self._log,
            )
        raise ValueError(f"Unsupported transport '{config.transport}' for backend '{config.name}'")

    def list_backends(self) -> list[BackendConfig]:
        return list(self._configs.values())

    def is_connected(self, name: str) -> bool:
        connector = self._connectors.get(name)
        return connector is not None and connector.is_connected

    def list_connected(self) -> list[str]:
        return [name for name, c in self._connectors.items() if c.is_connected]

    async def health_check_all(self) -> dict[str, dict]:
        results = {}
        for name, config in self._configs.items():
            connector = self._connectors.get(name)
            if connector is None:
                try:
                    connector = self.get_connector(name)
                except Exception as e:
                    self._log.warning("Health check: cannot build connector for '%s': %s", name, e)
                    results[name] = {"status": "unhealthy", "error": str(e), "consecutive_failures": 1}
                    continue
            if connector is None:
                results[name] = {"status": "unknown", "error": "not initialized", "consecutive_failures": 0}
                continue
            try:
                ok = await connector.health()
            except Exception as e:
                ok = False
                self._log.error("Health check exception for '%s': %s", name, e, exc_info=True)

            cache = self._health_cache.get(name, {"consecutive_failures": 0, "last_status": None})
            if ok:
                if cache.get("last_status") != "healthy":
                    self._log.info("Health check: backend '%s' is healthy (recovered)", name)
                cache["consecutive_failures"] = 0
                cache["last_status"] = "healthy"
            else:
                cache["consecutive_failures"] = cache.get("consecutive_failures", 0) + 1
                cf = cache["consecutive_failures"]
                if cf >= 3:
                    cache["last_status"] = "dead"
                    self._log.error("Health check: backend '%s' DEAD after %d failures", name, cf)
                    if connector.is_connected:
                        await connector.disconnect()
                        self._log.warning("Disconnected dead backend '%s'", name)
                elif cf == 1:
                    cache["last_status"] = "unhealthy"
                    self._log.warning("Health check: backend '%s' unhealthy (attempt %d/3)", name, cf)
                else:
                    cache["last_status"] = "unhealthy"
                    self._log.warning("Health check: backend '%s' still unhealthy (attempt %d/3)", name, cf)

            cache["last_check"] = time.time()
            self._health_cache[name] = cache
            results[name] = {
                "status": cache["last_status"],
                "consecutive_failures": cache["consecutive_failures"],
                "last_check": cache["last_check"],
            }
        return results

    async def disconnect_all(self) -> None:
        for connector in self._connectors.values():
            if connector.is_connected:
                await connector.disconnect()
        self._connectors.clear()
        self._log.debug("All backends disconnected")
