# Persistent strict enforcement patch

Author: Codex

## Restricted usage reports — 2026-11-20

The coordinator compares consecutive per-device app counters under daily-limit
and bedtime restrictions. It logs the first growth report and raises a Home
Assistant notification on continued growth. Missing or cached data, authorized
exceptions and local day changes break the comparison. The lock planner uses
an independent applied-limits read before acting on continued growth, and the
next fresh device reading verifies an issued lock. Verified bonus cancellations
are correlated with subsequent overrides during the same local day.

Regression coverage includes late and duplicate reports, counter resets,
authorized bonus and app exceptions, multiple devices, alert deduplication,
and same versus replacement overrides. Detection starts with the first usage
update Google reports. School-time usage is outside this comparison.

## Earlier enforcement patches

Base: `e4804751536146747be7c2b370ebdb7de310a90e`.
Local image: `familylink-homeassistant:20261116.1`, Linux ARM64.

## Changes

- Bonus cancellation HTTP 200 is described as acceptance, not verified success.
  Strict enforcement reads fresh applied limits and requires zero bonus minutes
  and no bonus override on the targeted device before reporting success.
  Missing data, read failures, unchanged overrides, and replacement bonuses do
  not count as successful enforcement.
- Identical persistent corrections continue after the former three-attempt cap.
  Retry delays are 90, 90, 180, 360, 720, then 900 seconds, capped thereafter.
  Actual timing is rounded up to a subsequent polling cycle. Newly identified
  overrides have their own retry identity. Existing HA intent protections remain.
- INFO logs report fresh strict checks and bonus verification results. The
  existing event's `last_try` remains false because retries no longer exhaust.
- An ARM64 Dockerfile packages the integration on the pinned deployed HA base.
  At startup it replaces the integration under the persistent config directory.
  Remove the old integration bind mount when using this image.

## Validation

582 integration tests passed using the project's pinned HA test dependencies;
`pip check` found no broken requirements. Tests cover retry backoff and recovery,
unchanged and replacement bonuses, failed or missing readback, delayed removal,
and disabled strict mode. Image compilation and source SHA-256 comparison passed.

## Limits

Verification observes Google's reported state, not the physical phone. It cannot
guarantee that a new override will not appear after the read. Non-bonus correction
success retains the existing API-acceptance meaning; subsequent polling detects
persistent discrepancies and now continues retrying. A persistent correction can
wait up to the 15-minute backoff plus polling time. No live bonus was deliberately
granted to test this patch. The authentication service is unchanged.

These changes are local and have not been committed or pushed. Preserve this
checkout and the release image until the patch is committed with user approval.

## Downtime repair — 2026-11-17

Release candidate `familylink-homeassistant:20261117.1` enables the weekday slot
alongside its hour update. Fresh readback must confirm enabled state and matching
hours before the weekly write reports success. Today's default enabled state
also accounts for a disabled weekday, while explicit today overrides retain
precedence. Downtime corrections retry on subsequent polls after 60 seconds,
without the previous escalation to a 15-minute cooldown.

Validation: 585 integration tests passed, including disabled weekday and
accepted-but-ineffective weekly write regressions; pip check and diff check clean.
Live deployment results are recorded in the parent project's EC2.md.

Deployment completed on dedicated EC2: all seven Tomas slot updates returned
verified=True, subsequent refresh planned zero corrections, both children's
seven-day schedules were enabled, and both devices reported bedtime_active=true.
Authentication container remained unchanged. No commit or push performed.

## Disabled daily-limit repair — 2026-11-18

Release `familylink-homeassistant:20261118.1` detects disabled weekly days even
when stored minutes match the parent reference, explicitly re-enables the slot,
and restores today's device quota when its effective limit is disabled. Parent
HA exceptions retain precedence; missing/unknown device state is not treated as
an explicit disable. Daily-limit corrections retry after 60 seconds.
Applied verification now requires enabled=true plus matching minutes; failed
reads do not count as success. Global-off weekly writes preserve day flags.
Validation: 590 tests passed, pip check and diff check clean. Added regressions
for global ON/day OFF, disabled effective quota, parent exceptions, missing
or disabled readback, and readback failure. Previous bonus and downtime fixes
are included in this reproducible ARM64 release.

Live release verification: restored seven disabled Tomas quota slots and one
Lucas slot; Tomas's 120-minute effective limit is enabled and his device reports
daily_limit_reached. Subsequent refreshes found zero corrections for both kids.
Both containers healthy. Rollback preserved on EC2.
