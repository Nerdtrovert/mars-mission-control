"""Raspberry Pi Hardware Gateway Package for Mars Mission Control."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repository root and backend directory are in sys.path
# so shared contracts (app.communication.gateway_contract, etc.) resolve on Raspberry Pi OS.
_root_dir = Path(__file__).resolve().parent.parent
_backend_dir = _root_dir / "backend"

if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if _backend_dir.is_dir() and str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))


def _load_env() -> None:
    """Load configuration from .env file if present, preserving existing environment variables."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        _root_dir / ".env",
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

__version__ = "1.0.0"
