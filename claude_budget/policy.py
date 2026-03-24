"""Budget policies that decide whether pipeline work should continue.

A policy is a callable: (utilization: float | None, hours_remaining: float | None) → bool
Returns True if work should continue, False if the pipeline should stop.

Built-in factories produce policies from user-facing parameters.
"""

from collections.abc import Callable
from datetime import timedelta

type Policy = Callable[[float | None, float | None], bool]


def flat_ceiling(ceiling: float) -> Policy:
    """Pipeline may use up to `ceiling` fraction of the budget.

    No time awareness — the ceiling is fixed regardless of when the reset occurs.
    """

    def policy(utilization: float | None, hours_remaining: float | None) -> bool:
        if utilization is None:
            return True
        return utilization < ceiling

    return policy


def reserve_per_hour(rate: float) -> Policy:
    """Reserve `rate` fraction of the budget per remaining hour.

    Ceiling = 1.0 - rate * hours_remaining, clamped to [0, 1].
    With rate=0.10 and 4 hours left, the pipeline may use up to 60%.
    """

    def policy(utilization: float | None, hours_remaining: float | None) -> bool:
        if utilization is None or hours_remaining is None:
            return True
        ceiling = max(0.0, min(1.0, 1.0 - rate * hours_remaining))
        return utilization < ceiling

    return policy


def back_by(back_in: timedelta, reserve: float = 0.30) -> Policy:
    """Ensure `reserve` fraction is available by `back_in` from now.

    Ceiling = 1.0 - reserve. When hours_remaining drops below back_in,
    the ceiling relaxes proportionally (budget is about to reset, less
    reservation needed).
    """
    back_in_hours = back_in.total_seconds() / 3600

    def policy(utilization: float | None, hours_remaining: float | None) -> bool:
        if utilization is None or hours_remaining is None:
            return True
        if hours_remaining < back_in_hours and back_in_hours > 0:
            fraction = hours_remaining / back_in_hours
            ceiling = 1.0 - reserve * fraction
        else:
            ceiling = 1.0 - reserve
        return utilization < ceiling

    return policy


def policy_from_config(config: dict) -> Policy:
    """Create a policy from a config dict (produced by interactive collection).

    Supported strategies:
        {"strategy": "flat_ceiling", "ceiling": 0.70}
        {"strategy": "reserve_per_hour", "rate": 0.10}
        {"strategy": "back_by", "back_in_hours": 1, "reserve": 0.30}
    """
    strategy = config.get("strategy")
    match strategy:
        case "flat_ceiling":
            return flat_ceiling(ceiling=config["ceiling"])
        case "reserve_per_hour":
            return reserve_per_hour(rate=config["rate"])
        case "back_by":
            return back_by(
                back_in=timedelta(hours=config["back_in_hours"]),
                reserve=config.get("reserve", 0.30),
            )
        case _:
            raise ValueError(f"Unknown policy strategy: {strategy!r}")
