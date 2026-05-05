import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


_DEFAULT_CONFIG = {
    "agora": {"name": "Agora", "version": "0.1.0"},
    "storage": {"chroma_path": "~/.agora/chroma", "db_path": "~/.agora/agora.db"},
    "cache": {"l1_max_entries": 1000, "l1_ttl_seconds": 300, "l2_max_entries": 10000, "l2_ttl_seconds": 86400},
    "embedding": {"provider": "sentence-transformers", "model": "all-MiniLM-L6-v2"},
}


@dataclass
class BackendConfig:
    name: str
    transport: str = "stdio"
    command: list[str] | None = None
    url: str | None = None
    description: str = ""
    read_only: bool = False
    timeout_seconds: float | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    name: str = "Agora"
    version: str = "0.1.0"
    chroma_path: str = "~/.agora/chroma"
    db_path: str = "~/.agora/agora.db"
    l1_max_entries: int = 1000
    l1_ttl_seconds: int = 300
    l2_max_entries: int = 10000
    l2_ttl_seconds: int = 86400
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "all-MiniLM-L6-v2"
    backends: list[BackendConfig] = field(default_factory=list)

    @property
    def resolved_chroma_path(self) -> Path:
        return Path(self.chroma_path).expanduser()

    @property
    def resolved_db_path(self) -> Path:
        return Path(self.db_path).expanduser()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        if path is None:
            env_path = os.environ.get("AGORA_CONFIG")
            if env_path:
                path = Path(env_path).expanduser()
        if path is None:
            candidates = [
                Path.cwd() / "config.yaml",
                Path.home() / ".agora" / "config.yaml",
            ]
            for c in candidates:
                if c.exists():
                    path = c
                    break
            else:
                return cls()
        path = Path(path).expanduser()
        with open(path) as f:
            raw = yaml.safe_load(f)
        a = raw.get("agora", {})
        s = raw.get("storage", {})
        c = raw.get("cache", {})
        e = raw.get("embedding", {})
        backends_raw = raw.get("backends", [])
        backends = []
        for b in backends_raw:
            env_raw = b.get("env", {})
            resolved_env = {
                k: os.path.expandvars(v) for k, v in env_raw.items()
            } if env_raw else {}
            backends.append(BackendConfig(
                name=b.get("name", ""),
                transport=b.get("transport", "stdio"),
                command=b.get("command"),
                url=b.get("url"),
                description=b.get("description", ""),
                read_only=b.get("read_only", False),
                timeout_seconds=b.get("timeout_seconds"),
                env=resolved_env,
            ))
        return cls(
            name=a.get("name", "Agora"),
            version=a.get("version", "0.1.0"),
            chroma_path=s.get("chroma_path", "~/.agora/chroma"),
            db_path=s.get("db_path", "~/.agora/agora.db"),
            l1_max_entries=c.get("l1_max_entries", 1000),
            l1_ttl_seconds=c.get("l1_ttl_seconds", 300),
            l2_max_entries=c.get("l2_max_entries", 10000),
            l2_ttl_seconds=c.get("l2_ttl_seconds", 86400),
            embedding_provider=e.get("provider", "sentence-transformers"),
            embedding_model=e.get("model", "all-MiniLM-L6-v2"),
            backends=backends,
        )
