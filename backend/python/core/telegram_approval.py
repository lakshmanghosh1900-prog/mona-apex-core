from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

from .config import settings

API = "https://api.telegram.org/bot{token}/{method}"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class ApprovalRecord:
    id: str
    task: str
    step: dict[str, Any]
    risk: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str | None = None
    resolved_by: str | None = None
    note: str = ""
    message_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "step": self.step,
            "risk": self.risk,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "note": self.note,
        }


class TelegramApprovalGate:
    def __init__(self) -> None:
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_admin_chat_id
        self._pending: dict[str, ApprovalRecord] = {}
        self._futures: dict[str, asyncio.Future[bool]] = {}
        self._task: asyncio.Task | None = None
        self._offset = 0
        self.enabled = settings.telegram_enabled

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._poll_loop(), name="telegram-approval-poll")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def request(self, task: str, step: dict[str, Any], timeout: int | None = None) -> bool:
        risk = self._assess_risk(step)
        record = ApprovalRecord(id=uuid.uuid4().hex[:12], task=task, step=step, risk=risk)
        self._pending[record.id] = record
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._futures[record.id] = future

        if not self.enabled:
            auto = settings.telegram_auto_approve
            self._resolve(record.id, ApprovalStatus.APPROVED if auto else ApprovalStatus.DENIED, "gateway-disabled")
            return auto

        sent = await self._send(record)
        if not sent:
            self._resolve(record.id, ApprovalStatus.ERROR, "telegram-unreachable")
            return settings.telegram_auto_approve

        try:
            return await asyncio.wait_for(future, timeout=timeout or settings.telegram_timeout)
        except asyncio.TimeoutError:
            self._resolve(record.id, ApprovalStatus.TIMEOUT, "approval-timed-out")
            await self._edit(record.id, "⏰ Approval timed out - action cancelled.")
            return False

    def queue(self) -> list[dict[str, Any]]:
        return [r.as_dict() for r in self._pending.values()]

    def resolve_locally(self, record_id: str, approved: bool, resolved_by: str = "api") -> bool:
        if record_id not in self._pending:
            return False
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        self._resolve(record_id, status, resolved_by)
        return True

    def _assess_risk(self, step: dict[str, Any]) -> str:
        tool = str(step.get("tool", "")).lower()
        if tool in {"http_fetch"}:
            return "medium"
        if tool in {"shell", "write_file", "send_email", "transfer", "deploy"}:
            return "critical"
        return "low"

    def _resolve(self, record_id: str, status: ApprovalStatus, resolved_by: str) -> None:
        record = self._pending.get(record_id)
        if record is None or record.status is not ApprovalStatus.PENDING:
            return
        record.status = status
        record.resolved_at = datetime.now(timezone.utc).isoformat()
        record.resolved_by = resolved_by
        future = self._futures.pop(record_id, None)
        if future is not None and not future.done():
            future.set_result(status is ApprovalStatus.APPROVED)

    async def _send(self, record: ApprovalRecord) -> bool:
        text = (
            " <b>Mona requires approval</b>\n\n"
            f"<b>Task:</b> {record.task[:500]}\n"
            f"<b>Tool:</b> <code>{record.step.get('tool', 'unknown')}</code>\n"
            f"<b>Risk:</b> {record.risk}\n"
            f"<b>Request id:</b> <code>{record.id}</code>"
        )
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"apx:{record.id}:allow"},
                        {"text": "❌ Deny", "callback_data": f"apx:{record.id}:deny"},
                    ]
                ]
            },
        }
        return await self._call("sendMessage", payload, record_id=record.id)

    async def _edit(self, record_id: str, text: str) -> None:
        record = self._pending.get(record_id)
        if record is None or record.message_id is None:
            return
        await self._call(
            "editMessageText",
            {
                "chat_id": self.chat_id,
                "text": text,
                "message_id": record.message_id,
                "parse_mode": "HTML",
            },
        )

    async def _call(self, method: str, payload: dict[str, Any], record_id: str | None = None) -> bool:
        if not self.token:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(API.format(token=self.token, method=method), json=payload)
            if res.status_code != 200:
                return False
            data = res.json()
            result = data.get("result")
            if record_id and isinstance(result, dict) and result.get("message_id"):
                record = self._pending.get(record_id)
                if record is not None:
                    record.message_id = int(result["message_id"])
            return bool(data.get("ok", False))
        except httpx.HTTPError:
            return False

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(1)

    async def _poll_once(self) -> None:
        payload = {"timeout": 20, "offset": self._offset, "allowed_updates": ["callback_query"]}
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(API.format(token=self.token, method="getUpdates"), json=payload)
        if res.status_code != 200:
            await asyncio.sleep(3)
            return
        for update in res.json().get("result", []):
            self._offset = int(update.get("update_id", self._offset)) + 1
            callback = update.get("callback_query")
            if not callback:
                continue
            data = callback.get("data") or ""
            if not data.startswith("apx:"):
                continue
            _, record_id, decision = data.split(":", 2)
            resolved_by = (callback.get("from") or {}).get("username") or str(callback.get("from", {}).get("id", "unknown"))
            status = ApprovalStatus.APPROVED if decision == "allow" else ApprovalStatus.DENIED
            self._resolve(record_id, status, resolved_by)
            await self._answer_callback(callback.get("id"))
            record = self._pending.get(record_id)
            emoji = "✅ Approved" if status is ApprovalStatus.APPROVED else "❌ Denied"
            await self._edit(record_id, f"{emoji} by @{resolved_by}\nTask: {(record.task if record else '')[:300]}")

    async def _answer_callback(self, callback_id: str | None) -> None:
        if not callback_id:
            return
        await self._call("answerCallbackQuery", {"callback_query_id": callback_id})
