"""Unit tests for budget policies."""

from datetime import timedelta

from claude_budget.policy import (
    Policy,
    back_by,
    flat_ceiling,
    policy_from_config,
    reserve_per_hour,
)


# ── flat_ceiling ─────────────────────────────────────────────────


def test_flat_ceiling_below():
    p = flat_ceiling(ceiling=0.60)
    assert p(0.50, 3.0) is True


def test_flat_ceiling_at():
    p = flat_ceiling(ceiling=0.60)
    assert p(0.60, 3.0) is False


def test_flat_ceiling_above():
    p = flat_ceiling(ceiling=0.60)
    assert p(0.80, 3.0) is False


def test_flat_ceiling_ignores_hours():
    p = flat_ceiling(ceiling=0.60)
    assert p(0.50, None) is True
    assert p(0.70, None) is False


def test_flat_ceiling_none_utilization_fails_open():
    p = flat_ceiling(ceiling=0.60)
    assert p(None, 3.0) is True


# ── reserve_per_hour ─────────────────────────────────────────────


def test_reserve_per_hour_basic():
    p = reserve_per_hour(rate=0.10)
    # 4 hours left → ceiling = 1.0 - 0.10 * 4 = 0.60
    assert p(0.50, 4.0) is True
    assert p(0.65, 4.0) is False


def test_reserve_per_hour_one_hour():
    p = reserve_per_hour(rate=0.10)
    # 1 hour left → ceiling = 0.90
    assert p(0.85, 1.0) is True
    assert p(0.95, 1.0) is False


def test_reserve_per_hour_ceiling_clamps_to_zero():
    p = reserve_per_hour(rate=0.30)
    # 5 hours left → ceiling = 1.0 - 0.30 * 5 = -0.50 → clamped to 0.0
    assert p(0.0, 5.0) is False


def test_reserve_per_hour_none_utilization_fails_open():
    p = reserve_per_hour(rate=0.10)
    assert p(None, 4.0) is True


def test_reserve_per_hour_none_hours_fails_open():
    p = reserve_per_hour(rate=0.10)
    assert p(0.50, None) is True


# ── back_by ──────────────────────────────────────────────────────


def test_back_by_below_ceiling():
    p = back_by(back_in=timedelta(hours=1), reserve=0.30)
    # ceiling = 1.0 - 0.30 = 0.70
    assert p(0.50, 3.0) is True


def test_back_by_above_ceiling():
    p = back_by(back_in=timedelta(hours=1), reserve=0.30)
    assert p(0.75, 3.0) is False


def test_back_by_at_ceiling():
    p = back_by(back_in=timedelta(hours=1), reserve=0.30)
    assert p(0.70, 3.0) is False


def test_back_by_high_reserve():
    p = back_by(back_in=timedelta(hours=2), reserve=0.50)
    # ceiling = 1.0 - 0.50 = 0.50
    assert p(0.40, 4.0) is True
    assert p(0.55, 4.0) is False


def test_back_by_none_utilization_fails_open():
    p = back_by(back_in=timedelta(hours=1), reserve=0.30)
    assert p(None, 3.0) is True


def test_back_by_none_hours_fails_open():
    p = back_by(back_in=timedelta(hours=1), reserve=0.30)
    assert p(0.50, None) is True


def test_back_by_zero_reserve():
    p = back_by(back_in=timedelta(hours=1), reserve=0.0)
    # ceiling = 1.0, so anything below 1.0 is fine
    assert p(0.99, 2.0) is True


def test_back_by_near_reset_relaxes():
    """When hours_remaining < back_in, ceiling relaxes proportionally."""
    p = back_by(back_in=timedelta(hours=2), reserve=0.40)
    # ceiling = 1.0 - 0.40 = 0.60 normally
    # But with only 0.5 hours left (< back_in of 2h), fraction = 0.5/2.0 = 0.25
    # relaxed ceiling = 1.0 - 0.40 * 0.25 = 0.90
    assert p(0.85, 0.5) is True
    assert p(0.95, 0.5) is False


# ── policy_from_config ───────────────────────────────────────────


def test_config_flat_ceiling():
    p = policy_from_config({"strategy": "flat_ceiling", "ceiling": 0.70})
    assert p(0.60, 3.0) is True
    assert p(0.75, 3.0) is False


def test_config_reserve_per_hour():
    p = policy_from_config({"strategy": "reserve_per_hour", "rate": 0.10})
    assert p(0.50, 4.0) is True


def test_config_back_by():
    p = policy_from_config({"strategy": "back_by", "back_in_hours": 1, "reserve": 0.30})
    assert p(0.50, 3.0) is True
    assert p(0.75, 3.0) is False


def test_config_back_by_defaults():
    p = policy_from_config({"strategy": "back_by", "back_in_hours": 1})
    # Should use default reserve
    assert p(0.50, 3.0) is True


def test_config_unknown_strategy_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown.*strategy"):
        policy_from_config({"strategy": "nonexistent"})


# ── Policy protocol ──────────────────────────────────────────────


def test_raw_callable_as_policy():
    """A plain lambda satisfies the Policy protocol."""
    p: Policy = lambda util, hrs: util < 0.70 if util is not None else True
    assert p(0.50, 3.0) is True
    assert p(0.80, 3.0) is False
