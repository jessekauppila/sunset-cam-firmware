---
title: systemd oneshot "runs but does nothing" — Python module missing its `__main__` entrypoint
date: 2026-06-15
category: docs/solutions/integration-issues
module: pi-firmware-boot
problem_type: integration_issue
component: boot-dispatcher
severity: high
symptoms:
  - "sunset-cam-boot.service (Type=oneshot) finishes status=0/SUCCESS in ~1-2s but starts nothing"
  - "Device boots, joins WiFi, never registers or heartbeats (the camera sits dark)"
  - "`python -m sunset_cam.boot` exits without executing main()"
tags: [systemd, oneshot, python, entrypoint, dunder-main, execstart, boot, onboarding, debugging]
---

# systemd oneshot "runs but does nothing" — Python module missing its `__main__` entrypoint

## Problem

Newly-commissioned camera 2 (`hw-sunset-cam-2`) was provisioned correctly — valid
`/opt/sunset-cam/config/config.json`, saved WiFi creds, correct firmware on
`feat/e-onboarding-stage1` — yet on every boot it joined WiFi and **sat dark**:
never registered, never heartbeated to prod.

## Symptoms

- `systemctl status sunset-cam-boot` → `active (exited)`, `status=0/SUCCESS`, ~1-2s, ~850ms CPU.
- No journal entries for `sunset-cam-supervisor` or `sunset-cam-setup` at any boot.
- `cameras.last_heartbeat_at` stayed NULL across multiple reboots.
- Yet `systemctl start sunset-cam-supervisor` *manually* worked perfectly.

## Root cause

`boot.py` defined `main()` but had **no `if __name__ == "__main__": main()`**.
The unit's `ExecStart=/opt/sunset-cam/.venv/bin/python -m sunset_cam.boot` therefore
imported the module, defined its functions, and exited **without ever calling
`main()`**. The dispatcher never ran — no `nmcli`, no `systemctl start`, nothing —
so the oneshot "succeeded" in ~1s having done nothing.

## What didn't work (and why it wasted ~3 hours)

The dispatcher logged nothing, so its silence was misread as "it ran and its
`systemctl start` was swallowed." That led to a string of wrong fixes:

- **`systemctl start --no-block`** — assumed a oneshot can't synchronously start a
  unit it's ordered `Before=`. Didn't help (the start was never even reached).
- **Removing `Before=…supervisor…setup`** from the unit. Didn't help either.
- **"It's a race" / "blocking vs --no-block"** — chasing timing differences between
  hand-written test scripts (which *explicitly called* the dispatcher and so worked)
  and `python -m sunset_cam.boot` (which never called `main()` and so didn't).

Every systemd theory was untestable noise because the code under suspicion never executed.

## Solution

Add the entrypoint:

```python
# src/sunset_cam/boot.py
def main() -> None:
    dispatch_boot(
        wifi_check=has_wifi_credentials,
        online_check=is_online,
        runner=_run,
        sleep=time.sleep,
    )


if __name__ == "__main__":
    main()
```

Secondary (only relevant once `main()` actually runs): the dispatcher starts the
chosen unit imperatively with a **blocking** `systemctl start` (no `--no-block`),
and `sunset-cam-boot.service` must **not** declare `Before=` those units — a unit
ordered after the still-activating oneshot can't be started from within its own
`ExecStart` (systemd drops the job). With the entrypoint + blocking start + no
ordering edge, a cold reboot brings the supervisor up unattended and it heartbeats.
Verified by two clean reboots (commit on `feat/e-onboarding-stage1`).

## Why this works

`python -m pkg.mod` sets `__name__ == "__main__"` for the module, but only code
guarded by `if __name__ == "__main__":` (or module top-level) actually runs. A bare
`def main()` is never invoked by `-m` without the guard.

## Prevention

- **Any module used as a systemd `ExecStart` (`python -m pkg.mod`) MUST have an
  `if __name__ == "__main__": main()` guard.** Add a regression test:

  ```python
  def test_running_module_as_main_invokes_the_dispatcher(monkeypatch):
      import runpy, subprocess, warnings
      calls = []
      class _C:  returncode = 0; stdout = ""; stderr = ""
      monkeypatch.setattr(subprocess, "run", lambda a, *x, **k: calls.append(list(a)) or _C())
      with warnings.catch_warnings():
          warnings.simplefilter("ignore", RuntimeWarning)
          runpy.run_module("sunset_cam.boot", run_name="__main__")
      assert any(c[:1] == ["nmcli"] for c in calls), "module run as __main__ didn't invoke main()"
  ```

- **Debugging discipline:** when a process "runs but does nothing," verify it
  *actually executes* (instrument it / confirm the entrypoint runs) **before**
  theorizing about systemd ordering, environment, or timing. A silent component is
  the blind spot. Cheap check: monkeypatch a dependency + `runpy.run_module(name,
  run_name="__main__")` — no calls means `main()` never ran.
- **Reproduce service bugs without rebooting:** `systemctl start <oneshot>` re-runs
  it in the real service context. Compare against running it as a plain process —
  a difference points at the unit/context, not the code.
- **Beware self-polluting tests:** rapid `systemctl stop`/`start` cleanups race the
  just-started unit. Run one clean test and touch nothing.

## Related

- `docs/solutions/integration-issues/lat-lng-arrive-as-strings-from-cloud-config.md`
- `docs/solutions/integration-issues/stacked-branch-missing-merged-dependency.md`
