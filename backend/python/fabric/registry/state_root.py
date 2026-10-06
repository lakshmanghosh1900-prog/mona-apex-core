"""Shared durable state root for all zero-cost registry subsystems.

Historical behavior hard-coded ``/tmp/mona_sandbox`` in every subsystem.
``/tmp`` is wiped on reboot and is not a portable persistence location
(gate P1), and there was no single knob to relocate state (gate P4).

Resolution order:
1. ``$MONA_STATE_DIR`` environment variable (explicit override)
2. ``~/.mona/sandbox`` (durable per-user default)

Every subsystem resolves its root via :func:`state_dir` so all state
memory/, audit/, execution/, tenants/, rate_limits/, evidence/,
observability/ lives under ONE configurable parent directory.
"""
from __future__ import annotations

import os
import pathlib

ENV_STATE_DIR = "MONA_STATE_DIR"

_DEFAULT_PARENT = pathlib.Path.home() / ".mona"
_DEFAULT_SANDBOX = "sandbox"


def get_state_root() -> pathlib.Path:
    """Return the canonical durable sandbox state root (created on demand)."""
    configured = os.getenv(ENV_STATE_DIR, "").strip()
    if configured:
        root = pathlib.Path(configured).expanduser()
    else:
        root = _DEFAULT_PARENT / _DEFAULT_SANDBOX
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return root


def state_dir(name: str) -> pathlib.Path:
    """Return (and ensure) a named subdirectory under the state root."""
    path = get_state_root() / name
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path
