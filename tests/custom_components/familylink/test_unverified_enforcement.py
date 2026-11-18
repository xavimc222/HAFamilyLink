"""Missing successful API responses must not create an enforcement blind spot."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.strict_mode import (
    unverified_devices, plan_unverified_locks, plan_strict_actions, STRICT_RULES,
)

DEVICES = [{"id": "phone", "locked": False}]
COMPLETE = {"devices": {"phone": {"bonus_minutes": 0, "daily_limit_enabled": True}}}


def test_empty_and_partial_success_are_unverified():
    assert unverified_devices(DEVICES, {}, True) == ["phone"]
    assert unverified_devices(DEVICES, {"devices": {"phone": {"bonus_minutes": 0}}}, True) == ["phone"]
    assert unverified_devices(DEVICES, COMPLETE, True) == []
    assert unverified_devices(DEVICES + [{"id": "tablet"}], COMPLETE, True) == ["tablet"]


def test_protective_lock_preserves_parent_exceptions_and_manual_lock():
    child = {"child_id": "kid", "unverified_devices": ["phone"]}
    actions = plan_unverified_locks(child, set(STRICT_RULES), {}, set())
    assert actions[0]["record"] == "auto_lock"
    assert actions[0]["unverified"] is True
    assert plan_unverified_locks(child, set(STRICT_RULES), {}, {"phone"}) == []
    assert plan_unverified_locks(child, set(STRICT_RULES), {"devices": {"phone": "unlock"}}, set()) == []
    assert plan_unverified_locks(child, set(), {}, set()) == []
    assert plan_unverified_locks(child, set(STRICT_RULES), {"devices": {"phone": "lock"}}, set())[0]["record"] == "lock"


@pytest.mark.asyncio
async def test_retry_recovers_missing_device_before_lock_needed():
    c = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    c.client = MagicMock()
    c.client.async_get_applied_time_limits = AsyncMock(side_effect=[{}, {}, COMPLETE])
    with patch('custom_components.familylink.coordinator.asyncio.sleep', new_callable=AsyncMock):
        result = await c._async_read_verified_limits(DEVICES, True, account_id='kid')
    assert result == COMPLETE
    assert c.client.async_get_applied_time_limits.await_count == 3


@pytest.mark.asyncio
async def test_persistent_empty_read_returns_unverified_after_three_attempts():
    c = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    c.client = MagicMock()
    c.client.async_get_applied_time_limits = AsyncMock(return_value={})
    with patch('custom_components.familylink.coordinator.asyncio.sleep', new_callable=AsyncMock):
        result = await c._async_read_verified_limits(DEVICES, True, account_id='kid')
    assert unverified_devices(DEVICES, result, True) == ['phone']
    assert c.client.async_get_applied_time_limits.await_count == 3


def test_recovery_lifts_protective_lock_only_when_restriction_over():
    child = {'child_id': 'kid', 'devices': [{'id': 'phone', 'locked': True}],
             'devices_time_data': {'phone': {'daily_limit_enabled': True, 'daily_limit_remaining': 0}}}
    intents = {'devices': {'phone': 'auto_lock'}}
    assert plan_strict_actions(child, {'lock'}, intents=intents) == []
    child['devices_time_data']['phone']['daily_limit_remaining'] = 40
    assert plan_strict_actions(child, {'lock'}, intents=intents)[0]['action'] == 'unlock_device'


@pytest.mark.asyncio
async def test_incomplete_poll_locks_without_claiming_healthy(caplog):
    c = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    c.client = MagicMock()
    c.is_strict_mode_enabled = MagicMock(return_value=True)
    c._intents_for = MagicMock(return_value={'policies': {}, 'devices': {}, 'values': {}})
    c._ha_bonus_devices = MagicMock(return_value=set())
    c._async_run_strict_action = AsyncMock()
    c.strict_rules = set(STRICT_RULES)
    c.strict_mode_status = {}
    child = {'child_id': 'kid', 'unverified_devices': ['phone'], 'applied_limits_fresh': False}
    await c._async_enforce_strict_mode({'children_data': [child]})
    assert c._async_run_strict_action.await_args.args[1]['action'] == 'lock_device'
    assert c.strict_mode_status['kid']['verified'] is False
    assert 'UNVERIFIED' in caplog.text
    assert 'fresh check' not in caplog.text


@pytest.mark.asyncio
async def test_transport_failure_retries_then_recovers():
    c = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    c.client = MagicMock()
    c.client.async_get_applied_time_limits = AsyncMock(side_effect=[TimeoutError(), COMPLETE])
    with patch('custom_components.familylink.coordinator.asyncio.sleep', new_callable=AsyncMock):
        assert await c._async_read_verified_limits(DEVICES, True, account_id='kid') == COMPLETE
    assert c.client.async_get_applied_time_limits.await_count == 2


def test_unsupported_devices_do_not_trigger_protective_locks():
    devices = [{'id': 'tv', 'capabilities': ['capabilityRing']}, {'id': 'phone', 'capabilities': ['capabilityBedtime']}]
    assert unverified_devices(devices, {}, True) == ['phone']


def test_unreadable_warning_redacts_values(caplog, monkeypatch):
    from custom_components.familylink.client import api
    monkeypatch.setattr(api, '_unreadable_logged', {})
    api._warn_unreadable('test', 'bad response', ['private-account', ['secret-override'], None])
    assert 'structure=' in caplog.text
    assert 'private-account' not in caplog.text
    assert 'secret-override' not in caplog.text
