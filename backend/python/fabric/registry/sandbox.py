from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fabric.registry.file_tool import is_contained, sandbox_root
from fabric.registry.registry_loader import get_registry
from fabric.registry.state_root import get_state_root, state_dir

TOOL_NAME = "code.run"
DEFAULT_TIMEOUT = 15
MAX_TIMEOUT = 60
MAX_OUTPUT_CHARS = 20_000
ENV_DENY_PREFIXES = ("MONA_", "GEMINI_", "GROQ_", "QWEN_", "OPENAI_", "ANTHROPIC_", "TELEGRAM_", "QDRANT_")
ENV_DENY_EXACT = frozenset({"AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "OPENAI_API_KEY"})
SANDBOX_LIMITS = (
    "process runs under the same OS user (no container/VM boundary)",
    "network access is not filtered (use docker_sandbox for network isolation)",
    "no cgroup memory/CPU limit is applied",
    "no seccomp/AppArmor profile is applied",
)


class SandboxTimeout(RuntimeError):
    pass


class SandboxPermissionError(PermissionError):
    pass


class SecureSandbox:
    """Stage 1.7 — isolation-verification harness for untrusted Python.

    Canonical ownership (gate D4): this class is NOT the production sandbox
    engine. Production code execution is owned exclusively by
    ``fabric.registry.execution_sandbox.ExecutionSandbox`` (DoD chain,
    apex, release, deploy). SecureSandbox exists solely to *verify* isolation
    guarantees: a fresh interpreter (`python -I`, so `PYTHON*` and user-site
    are ignored), cwd pinned to the sandbox root, a scrubbed environment (no
    API keys), a wall-clock timeout with process kill, and truncated output —
    semantics that only a real subprocess can demonstrate (child pid, timeout
    kill, env scrub, confined writes). This is a *soft* jail — see
    `SANDBOX_LIMITS` and `fabric/sandbox/` for what it deliberately does not
    claim.
    """

    # Ownership marker (D4): verification harness only, never production.
    CANONICAL_ROLE = "verification"

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else sandbox_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.execution_count = 0
        self.timeout_count = 0
        self.failure_count = 0

    # ---------- gates ----------
    def check_permission(self, role: str) -> bool:
        return get_registry().check_permission(TOOL_NAME, role)

    def _gate(self, role: str) -> None:
        if not self.check_permission(role):
            raise SandboxPermissionError(f"{TOOL_NAME} denied for role '{role}' (requires Operator+)")

    def child_env(self) -> dict[str, str]:
        env = {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(self.root)}
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "LANG"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    @staticmethod
    def scrub_env(env: dict[str, str]) -> dict[str, str]:
        return {
            key: value
            for key, value in env.items()
            if key not in ENV_DENY_EXACT and not key.startswith(ENV_DENY_PREFIXES)
        }

    # ---------- execution ----------
    def run_python(self, code: str, timeout: float = DEFAULT_TIMEOUT, role: str = "Operator") -> dict[str, Any]:
        self._gate(role)
        source = "" if code is None else str(code)
        if not source.strip():
            raise ValueError("code must be a non-empty string")
        limit = float(min(max(float(timeout), 1.0), MAX_TIMEOUT))

        self.execution_count += 1
        script = self.root / f"mona_exec_{self.execution_count:05d}.py"
        script.write_text(source, encoding="utf-8")

        started = time.perf_counter()
        timed_out = False
        returncode = -1
        stdout = ""
        stderr = ""
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [sys.executable, "-I", str(script)],
                cwd=str(self.root),
                env=self.child_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=limit,
                check=False,
            )
            returncode = completed.returncode
            stdout, stderr = completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            self.timeout_count += 1
            stdout = _as_text(exc.stdout)
            stderr = (_as_text(exc.stderr) or "") + f"\n[sandbox] terminated after {limit}s timeout"
        except Exception as exc:  # noqa: BLE001
            self.failure_count += 1
            stderr = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                script.unlink(missing_ok=True)
            except OSError:
                pass

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        truncated = len(stdout) > MAX_OUTPUT_CHARS or len(stderr) > MAX_OUTPUT_CHARS
        ok = returncode == 0 and not timed_out
        if not ok and not timed_out:
            self.failure_count += 1

        return {
            "tool": TOOL_NAME,
            "ok": ok,
            "stdout": stdout[:MAX_OUTPUT_CHARS],
            "stderr": stderr[:MAX_OUTPUT_CHARS],
            "returncode": returncode,
            "timed_out": timed_out,
            "timeout_seconds": limit,
            "duration_ms": duration_ms,
            "truncated": truncated,
            "cwd": str(self.root),
            "sandbox_root": str(self.root),
            "isolated": True,
            "env_scrubbed": True,
            "execution_count": self.execution_count,
            "cost_usd": 0.0,
        }

    # ---------- verification ----------
    def verify_isolation(self, role: str = "Operator") -> dict[str, Any]:
        probe_cwd = self.run_python("import os; print(os.getcwd())", timeout=10, role=role)
        probe_pid = self.run_python("import os; print(os.getpid())", timeout=10, role=role)
        probe_env = self.run_python(
            "import os; print([k for k in os.environ if k.startswith(('MONA_','GEMINI_','GROQ_','OPENAI_'))])",
            timeout=10,
            role=role,
        )
        probe_timeout = self.run_python("import time; time.sleep(30)", timeout=1, role=role)
        probe_write = self.run_python("open('isolation_probe.txt','w').write('x')", timeout=10, role=role)
        probe_path = self.root / "isolation_probe.txt"

        cwd = probe_cwd["stdout"].strip()
        checks = {
            "cwd_inside_sandbox": probe_cwd["ok"] and is_contained(self.root, Path(cwd)),
            "separate_interpreter": probe_pid["ok"] and probe_pid["stdout"].strip().isdigit(),
            "child_process": bool(probe_pid["stdout"].strip()) and int(probe_pid["stdout"].strip() or 0) != os.getpid(),
            "env_scrubbed": probe_env["ok"] and probe_env["stdout"].strip() in ("[]", ""),
            "timeout_kills_process": probe_timeout["timed_out"],
            "writes_confined_to_sandbox": probe_write["ok"] and probe_path.exists() and is_contained(self.root, probe_path),
        }
        probe_path.unlink(missing_ok=True)
        isolation_ok = all(checks.values())

        return {
            "ok": isolation_ok,
            "isolation_ok": isolation_ok,
            "checks": checks,
            "failed_checks": [name for name, ok in checks.items() if not ok],
            "sandbox_root": str(self.root),
            "canonical_root": str(get_state_root()),
            "cwd_reported": cwd,
            "execution_count": self.execution_count,
            "timeout_count": self.timeout_count,
            "isolation_level": "subprocess-jail (soft)",
            "limits": list(SANDBOX_LIMITS),
            "harden_with": "fabric.sandbox.docker_sandbox (container boundary)",
            "cost_usd": 0.0,
        }

    def stats(self) -> dict[str, Any]:
        return {
            "sandbox_root": str(self.root),
            "execution_count": self.execution_count,
            "timeout_count": self.timeout_count,
            "failure_count": self.failure_count,
            "default_timeout": DEFAULT_TIMEOUT,
            "max_timeout": MAX_TIMEOUT,
        }

    def reset(self) -> None:
        self.execution_count = 0
        self.timeout_count = 0
        self.failure_count = 0


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


_sandbox: SecureSandbox | None = None


def get_sandbox(root: Path | str | None = None) -> SecureSandbox:
    global _sandbox
    if _sandbox is None or root is not None:
        _sandbox = SecureSandbox(root=root)
    return _sandbox


def reset_sandbox() -> None:
    global _sandbox
    _sandbox = None