"""fabric.sandbox.docker_sandbox — Stage 1.7 code execution isolation.

Identical surface to `fabric.registry.sandbox`; kept as an explicit re-export
rather than a copy so the two namespaces cannot drift apart. Swap the
subprocess backend for a container runtime here when hard isolation (network
namespace, cgroup limits, read-only rootfs) is required — the Stage 1.7
verification endpoint already reports which guarantees are and are not
enforced.

Canonical Spec: MONA — Powered by Apex Core
"""

from __future__ import annotations

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