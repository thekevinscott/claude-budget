"""Budget enforcement: gates pipeline work against a policy.

The Budget class periodically checks usage and asks the policy whether
work should continue. When the policy says no, gate() raises BudgetExhausted.
The usage_budget context manager suppresses that exception so code after
the with block runs normally.

Typical usage:
    configure(back_in_hours=1, reserve=0.30)

    async with usage_budget() as budget:
        for item in items:
            await budget.gate()
            await process(item)
"""

import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from claude_budget.policy import Policy, back_by, flat_ceiling, policy_from_config, reserve_per_hour
from claude_budget.usage import UsageStatus, check_usage

_active_policy: Policy | None = None


def configure(
    *,
    back_in_hours: float | None = None,
    reserve: float = 0.30,
    ceiling: float | None = None,
    rate: float | None = None,
    policy: Policy | None = None,
    config: dict | None = None,
):
    """Set the active budget policy for this process.

    Call once at startup. usage_budget() will use this policy automatically.

    Strategies (pick one):
        configure(back_in_hours=1, reserve=0.30)  # "I'll be back in 1h, keep 30%"
        configure(ceiling=0.60)                     # "Pipeline may use up to 60%"
        configure(rate=0.10)                        # "Reserve 10% per remaining hour"
        configure(policy=my_callable)               # Custom policy function
        configure(config={"strategy": "back_by", "back_in_hours": 1, "reserve": 0.30})
    """
    global _active_policy

    if policy is not None:
        _active_policy = policy
    elif config is not None:
        _active_policy = policy_from_config(config)
    elif back_in_hours is not None:
        _active_policy = back_by(back_in=timedelta(hours=back_in_hours), reserve=reserve)
    elif ceiling is not None:
        _active_policy = flat_ceiling(ceiling=ceiling)
    elif rate is not None:
        _active_policy = reserve_per_hour(rate=rate)
    else:
        raise ValueError(
            "configure() requires at least one of: back_in_hours, ceiling, rate, policy, config"
        )
    return _active_policy


def get_policy() -> Policy:
    """Return the active policy, or raise if not configured."""
    if _active_policy is None:
        raise RuntimeError(
            "No budget policy configured. Call configure() before using usage_budget()."
        )
    return _active_policy


def reset():
    """Clear the active policy. Mainly useful for testing."""
    global _active_policy
    _active_policy = None


class BudgetExhausted(Exception):
    """Raised by Budget.gate() when the policy ceiling is hit."""

    def __init__(self, status: UsageStatus | None = None):
        self.status = status
        super().__init__("Budget exhausted")


def extract_utilization(status: UsageStatus) -> float | None:
    """Extract the five-hour utilization fraction from a UsageStatus.

    Returns a 0.0-1.0 value, or None if not available.
    """
    return status.five_hour


class Budget:
    """Enforces a usage policy by gating work submission."""

    def __init__(
        self,
        policy: Policy,
        poll_interval_seconds: float = 60,
        check_fn=check_usage,
    ):
        self._policy = policy
        self._poll_interval = poll_interval_seconds
        self._check_fn = check_fn
        self._status: UsageStatus | None = None
        self._last_poll: float | None = None
        self._exhausted = False

    @property
    def exhausted(self) -> bool:
        return self._exhausted

    @property
    def status(self) -> UsageStatus | None:
        return self._status

    async def gate(self):
        """Check whether work should continue. Raises BudgetExhausted if not."""
        now = time.monotonic()
        if self._last_poll is None or (now - self._last_poll) >= self._poll_interval:
            await self._poll()
            self._last_poll = now

        if not self._evaluate():
            self._exhausted = True
            raise BudgetExhausted(self._status)

    async def _poll(self):
        self._status = await self._check_fn()

    def _evaluate(self) -> bool:
        status = self._status
        if status is None:
            return True
        if status.error is not None:
            return True
        if not status.available and status.error is None:
            utilization = 1.0
            hours_remaining = (
                status.retry_after_seconds / 3600
                if status.retry_after_seconds is not None
                else None
            )
            return self._policy(utilization, hours_remaining)
        utilization = extract_utilization(status)
        hours_remaining = None
        if status.five_hour_resets_at is not None:
            delta = status.five_hour_resets_at - datetime.now(timezone.utc)
            hours_remaining = max(0.0, delta.total_seconds() / 3600)
        elif status.reset_timestamp is not None:
            hours_remaining = max(0.0, (status.reset_timestamp - time.time()) / 3600)
        return self._policy(utilization, hours_remaining)


@asynccontextmanager
async def usage_budget(
    policy: Policy | None = None,
    poll_interval_seconds: float = 60,
    check_fn=check_usage,
):
    """Context manager that gates work against a usage policy.

    If no policy is provided, uses the one set by configure().
    Yields a Budget. BudgetExhausted is suppressed so code after the
    with block runs normally.
    """
    if policy is None:
        policy = get_policy()
    budget = Budget(
        policy=policy,
        poll_interval_seconds=poll_interval_seconds,
        check_fn=check_fn,
    )
    try:
        yield budget
    except BudgetExhausted:
        pass
