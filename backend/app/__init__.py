"""Mars Mission Control Backend Application Package."""

import os
from pathlib import Path


def _load_env() -> None:
    """Load configuration from .env file if present, preserving existing environment variables."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for env_path in candidates:
        if env_path.is_file():
            try:
                from dotenv import load_dotenv
                load_dotenv(dotenv_path=env_path, override=False)
                return
            except ImportError:
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
                    return
                except Exception:
                    pass


_load_env()
