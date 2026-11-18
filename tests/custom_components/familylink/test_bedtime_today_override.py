"""Bedtime "today": only an override posted today speaks for today.

Google keeps the bedtime overrides of earlier weeks under the same weekday
code; one left from last week must not switch tonight's bedtime off.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.util import dt as dt_util

from custom_components.familylink.client.api import FamilyLinkClient

from unittest.mock import AsyncMock, MagicMock

CHILD_ID = "child-1"
BEDTIME_RULE = "802c3176-8b24-452c-9ccd-2b19aebe487c"
SCHOOL_RULE = "5c0d1f2e-1111-4222-8333-944455556666"


def _time_limit_data() -> list:
    """An unwrapped timeLimit payload: bedtime and school time switched on in the weekly policy."""
    return [
        [2, [["CAEQAQ", 1, 2, [20, 0], [7, 0], "1", "2", BEDTIME_RULE]], "1", "2", 1],
        [[["CAEQAQ", 1, 2, 120, "1", "2"]]],
        None,
        None,
        [1],
        [[BEDTIME_RULE, 1, 2, ["1", 0]], [SCHOOL_RULE, 2, 2, ["1", 0]]],
    ]


class _Response:
    def __init__(self, payload) -> None:
        self._payload = payload
        self.status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def json(self):
        return self._payload


def _client(response: _Response) -> FamilyLinkClient:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    client._get_session = AsyncMock(return_value=session)
    return client


def _with_bedtime_override(posted_at_ms: int, action: int) -> list:
    """The timeLimit payload plus one bedtime override (type 9) for today's weekday."""
    code = FamilyLinkClient._DAY_CODES[dt_util.now().isoweekday()]
    return _time_limit_data() + [[["override-1", str(posted_at_ms), 9, None, [action, [21, 0], [7, 0], code]]]]


def _ms(moment) -> int:
    return int(moment.timestamp() * 1000)


@pytest.mark.parametrize(
    ("posted", "expected"),
    [
        # Switched off "for tonight" today: off
        (lambda midnight: midnight + timedelta(hours=1), False),
        # Switched off "for tonight" a week ago, same weekday: the weekly rule applies again
        (lambda midnight: midnight - timedelta(days=7) + timedelta(hours=20), True),
    ],
)
async def test_only_an_override_posted_today_counts(posted, expected) -> None:
    midnight = dt_util.start_of_local_day()
    client = _client(_Response(payload=[[None, "1"], _with_bedtime_override(_ms(posted(midnight)), action=1)]))

    result = await client.async_get_time_limit(account_id=CHILD_ID)

    assert result["bedtime_enabled"] is True
    assert result["bedtime_enabled_today"] is expected


async def test_disabled_weekday_is_not_enabled_by_global_toggle() -> None:
    data = _time_limit_data()
    data[0][1][0][1] = dt_util.now().isoweekday()
    data[0][1][0][2] = 1
    client = _client(_Response([[None, '1'], data]))
    result = await client.async_get_time_limit(account_id=CHILD_ID)
    assert result['bedtime_enabled'] is True
    assert result['bedtime_enabled_today'] is False


@pytest.mark.parametrize('enabled,expected', [(False, False), (True, True)])
async def test_weekly_bedtime_requires_enabled_readback(enabled, expected) -> None:
    import json
    client = _client(_Response([]))
    client._weekly_slot_cache = {}
    client._async_get_weekly_bedtime_slot_id = AsyncMock(return_value='slot-1')
    client.async_get_time_limit = AsyncMock(return_value={'bedtime_schedule': [
        {'day': 1, 'enabled': enabled, 'start': [22, 0], 'end': [7, 30]},
    ]})
    session = await client._get_session()
    session.post.return_value = _Response([])
    assert await client.async_set_bedtime('22:00', '07:30', day=1, account_id=CHILD_ID) is expected
    payload = json.loads(session.post.call_args.kwargs['data'])
    assert payload[2][0][2] == [['slot-1', 2]]
    assert payload[2][0][3] == [['slot-1', [22, 0], [7, 30]]]
