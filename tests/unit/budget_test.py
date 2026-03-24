"""Unit tests for budget enforcement."""

import time

import pytest

from claude_budget.budget import (
    Budget,
    BudgetExhausted,
    configure,
    extract_utilization,
    get_policy,
    reset,
    usage_budget,
)
from claude_budget.usage import UsageStatus


# ── extract_utilization ──────────────────────────────────────────


def test_extract_utilization_from_status():
    status = UsageStatus(available=True, five_hour=0.42)
    assert extract_utilization(status) == 0.42


def test_extract_utilization_none_when_missing():
    status = UsageStatus(available=True)
    assert extract_utilization(status) is None


# ── Budget.gate() ────────────────────────────────────────────────


def _make_status(available=True, five_hour=None, retry_after=None, error=None):
    reset_ts = time.time() + retry_after if retry_after is not None else None
    return UsageStatus(
        available=available,
        five_hour=five_hour,
        retry_after_seconds=retry_after,
        reset_timestamp=reset_ts,
        error=error,
    )


def _always_allow(utilization, hours_remaining):
    return True


def _never_allow(utilization, hours_remaining):
    return False


def _async_check(status):
    """Return an async check_fn that returns the given status."""
    async def check_fn():
        return status
    return check_fn


async def test_gate_passes_when_policy_allows():
    status = _make_status(five_hour=0.30)
    budget = Budget(policy=_always_allow, check_fn=_async_check(status))
    await budget.gate()
    assert budget.exhausted is False


async def test_gate_raises_when_policy_denies():
    status = _make_status(five_hour=0.80)
    budget = Budget(policy=_never_allow, check_fn=_async_check(status))
    with pytest.raises(BudgetExhausted):
        await budget.gate()
    assert budget.exhausted is True


async def test_gate_rate_limited_always_exhausted():
    """429 response means utilization=1.0, any reasonable policy should deny."""
    status = _make_status(available=False, retry_after=3600)

    def policy(util, hrs):
        return util < 0.99 if util is not None else True

    budget = Budget(policy=policy, check_fn=_async_check(status))
    with pytest.raises(BudgetExhausted):
        await budget.gate()


async def test_gate_error_fails_open():
    """When the endpoint errors, allow work to continue."""
    status = _make_status(available=False, error="Connection refused")
    budget = Budget(policy=_never_allow, check_fn=_async_check(status))
    await budget.gate()
    assert budget.exhausted is False


async def test_gate_respects_poll_interval():
    """check_fn is not called on every gate(), only after interval elapses."""
    call_count = 0

    async def counting_check():
        nonlocal call_count
        call_count += 1
        return _make_status(five_hour=0.30)

    budget = Budget(policy=_always_allow, poll_interval_seconds=60, check_fn=counting_check)
    await budget.gate()
    await budget.gate()
    await budget.gate()
    assert call_count == 1


async def test_gate_first_call_always_polls():
    call_count = 0

    async def counting_check():
        nonlocal call_count
        call_count += 1
        return _make_status(five_hour=0.30)

    budget = Budget(policy=_always_allow, poll_interval_seconds=60, check_fn=counting_check)
    await budget.gate()
    assert call_count == 1


async def test_gate_re_polls_after_interval(monkeypatch):
    """After the poll interval elapses, gate() polls again."""
    call_count = 0
    fake_time = [0.0]

    async def counting_check():
        nonlocal call_count
        call_count += 1
        return _make_status(five_hour=0.30)

    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
    budget = Budget(policy=_always_allow, poll_interval_seconds=60, check_fn=counting_check)

    await budget.gate()
    assert call_count == 1

    fake_time[0] = 61.0
    await budget.gate()
    assert call_count == 2


async def test_gate_exposes_status():
    status = _make_status(five_hour=0.30)
    budget = Budget(policy=_always_allow, check_fn=_async_check(status))
    assert budget.status is None
    await budget.gate()
    assert budget.status is status


async def test_gate_hours_remaining_from_retry_after():
    """hours_remaining is derived from retry_after_seconds."""
    received = {}

    def capturing_policy(utilization, hours_remaining):
        received["utilization"] = utilization
        received["hours_remaining"] = hours_remaining
        return True

    status = _make_status(available=False, retry_after=7200)
    budget = Budget(policy=capturing_policy, check_fn=_async_check(status))
    await budget.gate()
    assert received.get("hours_remaining") == pytest.approx(2.0, abs=0.1)


# ── usage_budget context manager ─────────────────────────────────


async def test_context_manager_suppresses_budget_exhausted():
    status = _make_status(five_hour=0.80)
    async with usage_budget(policy=_never_allow, check_fn=_async_check(status)) as budget:
        await budget.gate()
    assert budget.exhausted is True


async def test_context_manager_propagates_other_exceptions():
    status = _make_status(five_hour=0.30)
    with pytest.raises(ValueError, match="boom"):
        async with usage_budget(policy=_always_allow, check_fn=_async_check(status)):
            raise ValueError("boom")


async def test_context_manager_normal_exit():
    status = _make_status(five_hour=0.30)
    async with usage_budget(policy=_always_allow, check_fn=_async_check(status)) as budget:
        await budget.gate()
    assert budget.exhausted is False


# ── configure / get_policy / reset ───────────────────────────────


@pytest.fixture(autouse=False)
def clean_policy():
    """Reset module-level policy state after test."""
    reset()
    yield
    reset()


def test_configure_back_by_returns_policy(clean_policy):
    p = configure(back_in_hours=1, reserve=0.30)
    assert callable(p)
    assert p is get_policy()


def test_configure_ceiling_returns_policy(clean_policy):
    p = configure(ceiling=0.60)
    assert callable(p)
    assert p(0.50, 3.0) is True
    assert p(0.65, 3.0) is False


def test_configure_rate_returns_policy(clean_policy):
    p = configure(rate=0.10)
    assert callable(p)


def test_configure_custom_policy(clean_policy):
    custom = lambda u, h: True
    p = configure(policy=custom)
    assert p is custom


def test_configure_from_config(clean_policy):
    p = configure(config={"strategy": "flat_ceiling", "ceiling": 0.70})
    assert callable(p)


def test_configure_no_args_raises(clean_policy):
    with pytest.raises(ValueError, match="requires at least one"):
        configure()


def test_get_policy_without_configure_raises(clean_policy):
    with pytest.raises(RuntimeError, match="No budget policy configured"):
        get_policy()


def test_reset_clears_policy(clean_policy):
    configure(ceiling=0.50)
    reset()
    with pytest.raises(RuntimeError):
        get_policy()


async def test_usage_budget_uses_configured_policy(clean_policy):
    configure(ceiling=0.90)
    status = _make_status(five_hour=0.30)
    async with usage_budget(check_fn=_async_check(status)) as budget:
        await budget.gate()
    assert budget.exhausted is False


async def test_usage_budget_no_config_raises(clean_policy):
    with pytest.raises(RuntimeError, match="No budget policy configured"):
        async with usage_budget(check_fn=_async_check(_make_status())):
            pass
