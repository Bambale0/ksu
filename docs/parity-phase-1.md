# Phase 1 — P0 functional parity blockers

Parent: #145

Scope:

- Durable hidden-history listing and restore after reload.
- Preset edit/update UI parity for `PUT /presets/{id}`.
- Capability-driven Feed actions for trend generations.
- Notification badge compatibility with the visible ROXY navigation.
- Focused regression coverage.

Exit criteria:

- Hidden generations can be restored after a cold reload.
- Existing presets can be edited without delete/recreate.
- Trend cards never offer forbidden remix/repeat actions.
- Unread notifications are visible on the actual active ROXY profile navigation item.
- Tests guard each behavior.
