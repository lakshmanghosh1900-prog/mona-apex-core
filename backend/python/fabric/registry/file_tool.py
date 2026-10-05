from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fabric.registry.registry_loader import get_registry

TOOL_READ = "files.read"
TOOL_WRITE = "files.write"

SANDBOX_ROOT = "/tmp/mona_sandbox"
ENV_SANDBOX_ROOT = "MONA_SANDBOX_ROOT"
MAX_READ_BYTES = 2_000_000
MAX_WRITE_BYTES = 2_000_000
MAX_SEARCH_MATCHES = 200
ORGANIZE_ACTIONS = ("move", "copy", "mkdir", "delete", "list")


class SandboxPathError(PermissionError):
    """Raised when a path escapes the sandbox root."""


class FilePermissionError(PermissionError):
    pass


def sandbox_root() -> Path:
    """Active sandbox root.

    Canonical location is `SANDBOX_ROOT` (`/tmp/mona_sandbox`) on POSIX. On
    Windows `/tmp` is not a real mount point, so the OS temp dir is used;
    override anywhere with MONA_SANDBOX_ROOT. The directory is created on
    demand.
    """
    override = os.getenv(ENV_SANDBOX_ROOT, "").strip()
    if override:
        root = Path(override).expanduser()
    elif os.name != "nt":
        root = Path(SANDBOX_ROOT)
    else:
        root = Path(tempfile.gettempdir()) / "mona_sandbox"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return root


def is_contained(root: Path, candidate: Path) -> bool:
    """True when `candidate` is `root` or lives under it."""
    try:
        resolved = candidate.resolve()
        base = root.resolve()
    except OSError:
        return False
    return resolved == base or base in resolved.parents


class FileTool:
    """Stage 1.5 — read / write / search / organize inside the sandbox.

    Every path is resolved against the sandbox root and rejected when it
    escapes it (`..`, absolute paths elsewhere, symlinks pointing out), so a
    tool call can never touch the host filesystem outside `/tmp`.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else sandbox_root()
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------- path safety ----------
    def safe_path(self, path: str | Path) -> Path:
        if path is None or str(path).strip() == "":
            raise SandboxPathError("path must be a non-empty string")
        raw = Path(str(path))
        candidate = raw if raw.is_absolute() else self.root / raw
        resolved = candidate.resolve()
        if not is_contained(self.root, resolved):
            raise SandboxPathError(
                f"path escapes sandbox: {path!r} is outside {self.root}"
            )
        return resolved

    def _rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix() or "."
        except ValueError:
            return path.as_posix()

    def _gate(self, tool_name: str, role: str) -> None:
        if not get_registry().check_permission(tool_name, role):
            raise FilePermissionError(f"{tool_name} denied for role '{role}'")

    # ---------- files ----------
    def read(self, path: str, role: str = "User", max_chars: int = 50_000) -> dict[str, Any]:
        self._gate(TOOL_READ, role)
        target = self.safe_path(path)
        if not target.exists():
            return {
                "tool": TOOL_READ,
                "ok": False,
                "exists": False,
                "path": self._rel(target),
                "error": f"file not found: {self._rel(target)}",
            }
        if target.is_dir():
            return {
                "tool": TOOL_READ,
                "ok": False,
                "exists": True,
                "path": self._rel(target),
                "error": f"path is a directory: {self._rel(target)}",
            }
        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            return {
                "tool": TOOL_READ,
                "ok": False,
                "exists": True,
                "path": self._rel(target),
                "error": f"file too large: {size} bytes (limit {MAX_READ_BYTES})",
            }
        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > max_chars
        return {
            "tool": TOOL_READ,
            "ok": True,
            "exists": True,
            "path": self._rel(target),
            "absolute_path": str(target),
            "content": content[:max_chars],
            "chars": len(content),
            "truncated": truncated,
            "bytes": size,
            "cost_usd": 0.0,
        }

    def write(self, path: str, content: str, role: str = "User", append: bool = False) -> dict[str, Any]:
        self._gate(TOOL_WRITE, role)
        text = "" if content is None else str(content)
        if len(text.encode("utf-8", errors="ignore")) > MAX_WRITE_BYTES:
            raise ValueError(f"content exceeds {MAX_WRITE_BYTES} bytes")
        target = self.safe_path(path)
        if target.is_dir():
            raise ValueError(f"path is a directory: {self._rel(target)}")
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        previous = target.read_text(encoding="utf-8", errors="replace") if (append and existed) else ""
        with target.open("a" if append else "w", encoding="utf-8") as fh:
            fh.write(text)
        return {
            "tool": TOOL_WRITE,
            "ok": True,
            "path": self._rel(target),
            "absolute_path": str(target),
            "bytes_written": len(text.encode("utf-8", errors="ignore")),
            "appended": bool(append and existed),
            "created": not existed,
            "cost_usd": 0.0,
            "content": previous + text if (append and existed) else text,
        }

    def search(
        self,
        pattern: str,
        role: str = "User",
        glob: str = "**/*",
        max_matches: int = MAX_SEARCH_MATCHES,
        use_regex: bool = True,
    ) -> dict[str, Any]:
        self._gate(TOOL_READ, role)
        if not pattern:
            raise ValueError("pattern must be a non-empty string")
        regex = re.compile(pattern if use_regex else re.escape(pattern))
        matches: list[dict[str, Any]] = []
        files_scanned = 0
        truncated = False

        for candidate in sorted(self.root.glob(glob)):
            if truncated or not candidate.is_file():
                continue
            if not is_contained(self.root, candidate):
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files_scanned += 1
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(
                        {"path": self._rel(candidate), "line": lineno, "text": line.strip()[:400]}
                    )
                    if len(matches) >= max_matches:
                        truncated = True
                        break

        return {
            "tool": TOOL_READ,
            "ok": True,
            "pattern": pattern,
            "matches": matches,
            "match_count": len(matches),
            "files_scanned": files_scanned,
            "truncated": truncated,
            "sandbox_root": str(self.root),
            "cost_usd": 0.0,
        }

    def organize(self, action: str, src: str | None = None, dest: str | None = None, role: str = "Operator") -> dict[str, Any]:
        self._gate(TOOL_WRITE, role)
        verb = str(action).strip().lower()
        if verb not in ORGANIZE_ACTIONS:
            raise ValueError(f"unsupported action '{action}', expected one of {ORGANIZE_ACTIONS}")

        stamp = datetime.now(timezone.utc).isoformat()
        if verb == "mkdir":
            target = self.safe_path(dest or src or ".")
            target.mkdir(parents=True, exist_ok=True)
            return {"tool": TOOL_WRITE, "ok": True, "action": "mkdir", "path": self._rel(target), "timestamp": stamp}

        if verb == "list":
            base = self.safe_path(src or ".")
            if not base.is_dir():
                raise ValueError(f"not a directory: {self._rel(base)}")
            entries = []
            for item in sorted(base.rglob("*")):
                if is_contained(self.root, item):
                    entries.append(
                        {
                            "path": self._rel(item),
                            "is_dir": item.is_dir(),
                            "bytes": item.stat().st_size if item.is_file() else 0,
                        }
                    )
            return {
                "tool": TOOL_WRITE,
                "ok": True,
                "action": "list",
                "path": self._rel(base),
                "entries": entries,
                "count": len(entries),
                "timestamp": stamp,
            }

        if verb == "delete":
            target = self.safe_path(src or "")
            if target == self.root.resolve():
                raise SandboxPathError("refusing to delete the sandbox root")
            if not target.exists():
                raise FileNotFoundError(f"path not found: {self._rel(target)}")
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return {"tool": TOOL_WRITE, "ok": True, "action": "delete", "path": self._rel(target), "timestamp": stamp}

        if not src or not dest:
            raise ValueError(f"action '{verb}' requires both src and dest")
        source = self.safe_path(src)
        target = self.safe_path(dest)
        if not source.exists():
            raise FileNotFoundError(f"path not found: {self._rel(source)}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if verb == "move":
            shutil.move(str(source), str(target))
        else:
            if source.is_dir():
                shutil.copytree(str(source), str(target), dirs_exist_ok=True)
            else:
                shutil.copy2(str(source), str(target))
        return {
            "tool": TOOL_WRITE,
            "ok": True,
            "action": verb,
            "src": self._rel(source),
            "dest": self._rel(target),
            "timestamp": stamp,
        }

    # ---------- housekeeping ----------
    def stats(self) -> dict[str, Any]:
        files = [p for p in self.root.rglob("*") if p.is_file() and is_contained(self.root, p)]
        return {
            "sandbox_root": str(self.root),
            "canonical_root": SANDBOX_ROOT,
            "files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
            "contained": all(is_contained(self.root, p) for p in files),
        }

    def reset(self) -> None:
        for item in list(self.root.rglob("*")):
            if not is_contained(self.root, item):
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)


_tool: FileTool | None = None


def get_file_tool(root: Path | str | None = None) -> FileTool:
    global _tool
    if _tool is None or root is not None:
        _tool = FileTool(root=root)
    return _tool


def reset_file_tool() -> None:
    global _tool
    _tool = None