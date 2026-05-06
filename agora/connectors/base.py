import asyncio
import logging
import time
from abc import ABC, abstractmethod

_READ_TOOL_PREFIXES = ("list_", "get_", "fetch_", "read_", "search_", "find_", "query_", "describe_", "show_")


class ReadOnlyBlockedError(Exception):
    pass


class BackendConnector(ABC):
    def __init__(
        self,
        name: str,
        description: str,
        read_only: bool,
        transport: str = "stdio",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        rate_limit_rps: float = 0.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._read_only = read_only
        self._transport = transport
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._rate_limit_rps = rate_limit_rps
        self._connected = False
        self._log = logger or logging.getLogger(f"agora.connector.{name}")
        self._last_call_time: float = 0.0
        self._throttled_count: int = 0
        self._retry_total: int = 0

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

    async def health(self) -> bool:
        if not self._connected:
            return False
        try:
            async with asyncio.timeout(5):
                await self.list_tools()
                return True
        except Exception:
            self._connected = False
            return False

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if self._read_only and not tool_name.startswith(_READ_TOOL_PREFIXES):
            raise ReadOnlyBlockedError(
                "Backend '{}' is read-only, tool '{}' blocked. Allowed prefixes: {}".format(
                    self._name, tool_name, ", ".join(_READ_TOOL_PREFIXES)
                )
            )
        await self._apply_rate_limit()
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._call_tool_impl(tool_name, arguments)
            except (ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                self._retry_total += 1
                if attempt == self._max_retries:
                    self._log.error("call_tool FAILED after %d retries: %s - %s", self._max_retries, tool_name, e)
                    raise
                delay = min(self._retry_delay * (2**attempt), 30)
                self._log.warning(
                    "Retry %d/%d for '%s' tool '%s' after %.1fs: %s",
                    attempt + 1,
                    self._max_retries,
                    self._name,
                    tool_name,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)
            except Exception as e:
                self._log.error("call_tool ERROR (no retry): %s - %s", tool_name, e, exc_info=True)
                raise
        raise last_error

    @abstractmethod
    async def _call_tool_impl(self, tool_name: str, arguments: dict) -> dict: ...

    async def _apply_rate_limit(self) -> None:
        if self._rate_limit_rps <= 0:
            return
        interval = 1.0 / self._rate_limit_rps
        now = time.monotonic()
        elapsed = now - self._last_call_time
        if elapsed < interval:
            sleep_time = interval - elapsed
            self._throttled_count += 1
            self._log.debug("Throttled for %.3fs (rate limit: %.1f rps)", sleep_time, self._rate_limit_rps)
            await asyncio.sleep(sleep_time)
        self._last_call_time = time.monotonic()

    def throttled_count(self) -> int:
        return self._throttled_count

    def retry_total(self) -> int:
        return self._retry_total
