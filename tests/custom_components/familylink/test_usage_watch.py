"""Replay restricted usage reports, including Google's delayed app totals."""
from datetime import datetime, timedelta, timezone

from custom_components.familylink.usage_watch import observe_usage
from custom_components.familylink.strict_mode import plan_strict_actions, STRICT_RULES

NOW = datetime(2026, 11, 20, 20, tzinfo=timezone.utc)


def snapshot(seconds, *, bonus=False, bedtime=False, fresh=True, unlimited=False):
    return {
        "child_id": "c", "devices": [{"id": "phone", "locked": False}],
        "usage_fresh": fresh, "applied_limits_fresh": True, "time_limit_fresh": True,
        "downtime_unlimited_apps": False,
        "screen_time": {"date": NOW.date(), "device_screen_time": {
            "phone": {"app_breakdown": {"pkg": seconds}},
            "other": {"app_breakdown": {"pkg": 9000}}}},
        "devices_time_data": {"phone": {"daily_limit_enabled": True, "daily_limit_remaining": 0,
            "bedtime_active": bedtime, "bonus_minutes": int(bonus)*30,
            "bonus_override_id": "override" if bonus else None}},
        "apps": [{"packageName": "pkg", "supervisionSetting": {
            "alwaysAllowedAppInfo": {"enabled": True} if unlimited else None}}],
    }


def read(prev, child, elapsed=30, authorized=False):
    return observe_usage(prev, child, "phone", set(STRICT_RULES), authorized,
                         NOW + timedelta(seconds=elapsed), 70)


def test_cancel_then_growth_and_late_reports():
    prev, _ = read(None, snapshot(10, bonus=True), 0)
    prev, delta = read(prev, snapshot(10))
    assert not delta
    prev, delta = read(prev, snapshot(500), 60)
    assert delta == {"pkg": 490} and prev.reports == 1
    prev, delta = read(prev, snapshot(500), 90)
    assert not delta and prev.reports == 1
    prev, delta = read(prev, snapshot(510), 120)
    assert prev.reports == 2 and prev.growth == {"pkg": 500}
    assert not read(prev, snapshot(0), 150)[1]
    assert not read(prev, snapshot(900), 300)[1]


def test_exceptions_and_missing_data():
    prev, _ = read(None, snapshot(10), 0)
    assert read(prev, snapshot(100), authorized=True) == (None, {})
    assert read(prev, snapshot(100, fresh=False)) == (None, {})
    assert not read(prev, snapshot(100, unlimited=True))[1]
    prev, _ = read(None, snapshot(10, bedtime=True, unlimited=True), 0)
    assert read(prev, snapshot(100, bedtime=True, unlimited=True))[1] == {"pkg": 90}
    assert read(prev, snapshot(100), 86400) == (None, {})


def test_relock_requires_independent_evidence_and_respects_parent():
    child = snapshot(30)
    child["continued_usage_devices"] = ["phone"]
    def locks(authorized):
        return [a for a in plan_strict_actions(child, set(STRICT_RULES), authorized, {}, today=5)
                if a["action"] == "lock_device"]
    assert not locks(set())
    child["devices_time_data"]["phone"]["bonus_minutes"] = 30
    assert locks(set())[0]["verify_usage_bypass"]
    assert not locks({"phone"})


async def test_growth_alert_emitted_once_and_stale_gap_resets():
    from unittest.mock import AsyncMock, MagicMock, patch
    from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator

    c = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    c.hass = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._usage_windows = {}
    c._usage_locks_pending = set()
    c._ha_bonus_until = {}
    c.strict_rules = set(STRICT_RULES)
    c.is_strict_mode_enabled = lambda _: True
    c.strict_intents_today = lambda _: {"devices": {}}
    c.update_interval = timedelta(seconds=30)
    for index, seconds in enumerate([10, 100, 100, 150, 180]):
        with patch("custom_components.familylink.coordinator.dt_util.now", return_value=NOW+timedelta(seconds=index*30)):
            child = snapshot(seconds)
            await c._observe_usage({"children_data": [child]})
    c.hass.services.async_call.assert_awaited_once()
    assert child["continued_usage_devices"] == ["phone"]
    assert c._usage_windows["c", "phone"].growth == {"pkg": 170}
    await c._observe_usage({"children_data": [snapshot(200, fresh=False)]})
    assert not c._usage_windows
