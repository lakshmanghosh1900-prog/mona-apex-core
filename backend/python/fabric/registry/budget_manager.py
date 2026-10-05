from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


class BudgetManager:
    """Tracks spend against a daily budget.

    Mona's default stack is $0: every tool reports `cost = 0.0`, the daily
    limit is 0.0 and `can_spend(0.0)` stays True. The structure is ready for
    a future paid fallback — set a limit and costs become enforceable.
    """

    def __init__(self, daily_limit_usd: float = 0.0) -> None:
        self.daily_limit_usd = float(daily_limit_usd)
        self._spend: dict[str, float] = {}
        self._calls = 0

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def spend(self, amount_usd: float, tool_name: str | None = None) -> bool:
        if amount_usd < 0:
            raise ValueError("amount must be >= 0")
        if not self.can_spend(amount_usd):
            return False
        if amount_usd:
            day = self._today()
            self._spend[day] = self._spend.get(day, 0.0) + float(amount_usd)
        self._calls += 1
        return True

    def spent_today(self) -> float:
        return round(self._spend.get(self._today(), 0.0), 6)

    def remaining_today(self) -> float:
        return round(max(0.0, self.daily_limit_usd - self.spent_today()), 6)

    def can_spend(self, amount_usd: float) -> bool:
        return self.spent_today() + float(amount_usd) <= self.daily_limit_usd + 1e-9

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def zero_cost(self) -> bool:
        return self.spent_today() == 0.0 and self.daily_limit_usd == 0.0

    def check(self, tool_cost_usd: float = 0.0, limit_usd: float | None = None) -> dict[str, Any]:
        limit = self.daily_limit_usd if limit_usd is None else float(limit_usd)
        allowed = self.spent_today() + tool_cost_usd <= limit + 1e-9
        return {
            "allowed": allowed,
            "spent_today": self.spent_today(),
            "remaining_today": round(max(0.0, limit - self.spent_today()), 6),
            "limit_per_day": limit,
            "currency": "USD",
            "stack": "zero-cost",
        }

    def reset(self) -> None:
        self._spend.clear()
        self._calls = 0
