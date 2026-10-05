"""Phase 1 / Stage 1.7 — container-namespace mirror of the code sandbox.

The implementation lives in `fabric.registry.sandbox` (single source of
truth, next to the rest of the tool mesh). This package re-exports it so
callers can import from either namespace:

    from fabric.sandbox.docker_sandbox import SecureSandbox
    from fabric.registry.sandbox import SecureSandbox   # same class

Canonical Spec: MONA — Powered by Apex Core
"""

from fabric.registry.sandbox import (
    DEFAULT_TIMEOUT,
    ENV_DENY_EXACT,
    ENV_DENY_PREFIXES,
    MAX_OUTPUT_CHARS,
    MAX_TIMEOUT,
    SANDBOX_LIMITS,
    TOOL_NAME,
    SandboxPermissionError,
    SandboxTimeout,
    SecureSandbox,
    get_sandbox,
    reset_sandbox,
)

__all__ = [
    "DEFAULT_TIMEOUT",
    "ENV_DENY_EXACT",
    "ENV_DENY_PREFIXES",
    "MAX_OUTPUT_CHARS",
    "MAX_TIMEOUT",
    "SANDBOX_LIMITS",
    "TOOL_NAME",
    "SandboxPermissionError",
    "SandboxTimeout",
    "SecureSandbox",
    "get_sandbox",
    "reset_sandbox",
]