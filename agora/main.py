from agora.config import Config
from agora.logging import setup_logging
from agora.server import create_server


def main():
    logger = setup_logging()
    logger.info("Starting Agora...")
    config = Config.load()
    logger.info("Config loaded: version=%s, backends=%d", config.version, len(config.backends))
    mcp = create_server(config, logger=logger)
    mcp.run()
    logger.info("Agora stopped")


if __name__ == "__main__":
    main()
