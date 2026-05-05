from agora.config import Config
from agora.server import create_server


def main():
    config = Config.load()
    mcp = create_server(config)
    mcp.run()


if __name__ == "__main__":
    main()
