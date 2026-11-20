"""Compare per-device usage counters from adjacent fresh Family Link polls."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .strict_mode import restriction_active


@dataclass
class UsageWindow:
    day: str
    restriction: str
    observed: datetime
    counters: dict[str, float]
    growth: dict[str, float] = field(default_factory=dict)
    reports: int = 0


def observe_usage(previous: UsageWindow | None, child: dict[str, Any], device: str,
                  rules: set[str], authorized: bool, now: datetime, max_gap: float):
    """Return the next baseline and newly reported increments in seconds."""
    usage = child.get("screen_time") or {}
    day = now.date().isoformat()
    if (authorized or not child.get("usage_fresh") or not child.get("time_limit_fresh")
            or not child.get("applied_limits_fresh") or str(usage.get("date")) != day):
        return None, {}
    row = child["devices_time_data"].get(device, {})
    restriction = restriction_active(row)
    rule = {"bedtime": "bedtime", "daily limit reached": "daily_limit"}.get(restriction)
    if rule is None or rule not in rules or (row.get("bonus_override_id") and "bonus" not in rules):
        return None, {}
    data = usage.get("device_screen_time", {}).get(device, {}).get("app_breakdown")
    if data is None:
        return None, {}
    counters = {}
    for app in child["apps"]:
        package = app.get("packageName")
        if not package or (app.get("deviceIds") and device not in app["deviceIds"]):
            continue
        unlimited = (app.get("supervisionSetting") or {}).get("alwaysAllowedAppInfo")
        if unlimited and (rule != "bedtime" or child.get("downtime_unlimited_apps") is not False):
            continue
        counters[package] = data.get(package, 0)
    sample = UsageWindow(day, restriction, now, counters)
    if (previous is None or previous.day != day or previous.restriction != restriction
            or not 0 < (now - previous.observed).total_seconds() <= max_gap):
        return sample, {}
    common = counters.keys() & previous.counters.keys()
    if any(counters[p] < previous.counters[p] for p in common):
        return sample, {}
    delta = {p: counters[p] - previous.counters[p] for p in common if counters[p] > previous.counters[p]}
    sample.growth = previous.growth.copy()
    sample.reports = previous.reports + bool(delta)
    for p, seconds in delta.items():
        sample.growth[p] = sample.growth.get(p, 0) + seconds
    return sample, delta
