import asyncio
import sys

# Windows: SelectorEventLoop è più stabile con stdio pipes rispetto a ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from agora.config import Config
from agora.logging import setup_logging
from agora.server import create_server


def main():
    logger = setup_logging()
    logger.info("Starting Agora...")
    config = Config.load()
    logger.info("Config loaded: version=%s, backends=%d", config.version, len(config.backends))
    mcp = create_server(config, logger=logger)
    try:
        mcp.run()
    except Exception as e:
        logger.exception("Agora crashed: %s", e)
        raise
    logger.info("Agora stopped")


if __name__ == "__main__":
    main()
