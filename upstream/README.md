# atsdk (at_python) upstream contributions

Bugs found while building this migration on the Python atSign SDK, packaged for
upstream. Verified against atsdk 0.2.69 (PyPI) / 0.2.70 (repo `trunk`).
Upstream repo: https://github.com/atsign-foundation/at_python

## Bug → PR / issue map

| # | Bug | Deliverable | Location |
|---|-----|-------------|----------|
| 1 | `notify()` crashes without iv_nonce | **PR** `fix/notify-iv-nonce-and-session-id` | [prs/pr-1](prs/pr-1-notify-iv-nonce-session-id.md) |
| 2 | `session_id` default evaluated once at import | **PR** (same as #1) | [prs/pr-1](prs/pr-1-notify-iv-nonce-session-id.md) |
| 3 | Shared-key notifications never detected (`to_string` not called) | **PR** `fix/shared-key-notification-detection` | [prs/pr-2](prs/pr-2-shared-key-notification-detection.md) |
| 7 | Shared-key decrypt error hides the real exception (`- e`) | **PR** `fix/decrypt-error-detail` | [prs/pr-3](prs/pr-3-decrypt-error-detail.md) |
| 8 (primary) | `disconnect()` leaves `_connected=True` on failed close → monitor never recovers | **PR** `fix/disconnect-resets-connected` | [prs/pr-4](prs/pr-4-disconnect-resets-connected.md) |
| 4 | First-contact notification dropped on decrypt | **Issue** | [issues/issue-4](issues/issue-4-first-contact-decrypt-drop.md) |
| 5 | Monitor can't resume after client recreation | **Issue** | [issues/issue-5](issues/issue-5-monitor-resume-on-reconnect.md) |
| 6 | Long-lived client "Failed to decrypt shared_key…" after a while | **Issue** (unblocked by PR #7) | [issues/issue-6](issues/issue-6-long-lived-shared-key-decrypt-failure.md) |
| 8 (factors) | monitor no-recovery: global locks + zombie heartbeat thread | **Issue** | [issues/issue-8](issues/issue-8-monitor-no-recovery-after-drop.md) |

- Full technical catalogue: [atsdk-findings.md](atsdk-findings.md)
- Runnable, network-free repros: [repro/](repro/)

## Status
All 4 PR branches pushed to `atsign-foundation/at_python`, each lint-clean (CI flake8
hard gate) and test-backed (network-free `test/*_test.py`). Open the PRs at:
`https://github.com/atsign-foundation/at_python/pull/new/<branch>`.
