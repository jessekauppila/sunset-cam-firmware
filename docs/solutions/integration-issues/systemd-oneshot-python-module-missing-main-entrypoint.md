---
title: systemd oneshot "runs but does nothing" — Python module missing its `__main__` entrypoint
date: 2026-06-15
last_updated: 2026-06-15
category: docs/solutions/integration-issues
module: pi-firmware-boot
problem_type: integration_issue
component: boot-dispatcher
severity: high
symptoms:
  - "sunset-cam-boot.service (Type=oneshot) finishes status=0/SUCCESS in ~1-2s but starts nothing"
  - "Device boots, joins WiFi, never registers or heartbeats (the camera sits dark)"
  - "`python -m sunset_cam.boot` exits without executing main()"
tags: [systemd, oneshot, python, entrypoint, dunder-main, execstart, boot, onboarding, debugging, integration-test, entrypoint-smoke-test, untested-seam, context-saturation, feedback-loop]
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

## The deeper root cause (second pass, 2026-06-15): an untested-entrypoint *class*

The missing guard was not a one-off — it was one instance of a class: **the path
systemd actually runs (`python -m pkg.mod` → `main()` → real config + real IO) was
never exercised by any test.** Every boot test injected fakes into `dispatch_boot(...)`;
nothing ran `main()` or the module as `__main__`. The suite was green the entire time
the device sat dark.

The same untested seam produced the *sibling* bugs in this same onboarding arc — each
a "wired-up `main()` against a realistic config" defect, none caught by unit tests:

- `supervisor.main()` called the strict `load_config`, which rejects an unplaced
  device that only has identity → forced adding `load_identity` (commit `4f1456a`).
- `write_identity` dropped `hardware_id`, so register would 409 against the cloud
  (commit `582cba7`).

**Audit of all five systemd `ExecStart` entrypoints (updated 2026-06-16 after the
class was closed — see `tests/test_entrypoints_smoke.py`):**

| Entrypoint | `__main__` guard | Entrypoint smoke test |
|---|---|---|
| `sunset_cam.boot` (`-m`) | yes | yes (`runpy` test in `test_boot.py`) |
| `sunset_cam.supervisor` (`-m`) | yes | yes (behavioral — identity-only config) |
| `sunset_cam.main` (`-m`) | yes | yes (behavioral — argv + one in-window upload) |
| `scripts/run-setup-server.py` | yes | guard-only* |
| `scripts/run-setup-app.py` | yes | guard-only |

\* `run-setup-server.py` does `import smbus2` at module top, so it can't be imported
off-Pi for a behavioral smoke. The missing-`__main__` mode is covered by a
unit-file-discovered guard test that asserts every `ExecStart` target has a
`__main__: main()` guard (present and future units). To enable a behavioral smoke,
make the `smbus2` import lazy (inside `main()`, like `capture_jpeg` already is).

The fix + regression test closed the *instance* in `boot`; `test_entrypoints_smoke.py`
then closed the *class*: the missing-guard mode is guarded for all five entrypoints,
and `supervisor`/`main` have behavioral smokes that exercise the real `main()` wiring
against a realistic config (the `supervisor` one fails if `load_identity` ever regresses
back to the strict `load_config`). Remaining: a behavioral smoke for `run-setup-app.py`
and lazy `smbus2` to unblock one for `run-setup-server.py`.

## Why it stayed hidden for ~3 hours (the process root cause)

Two blind spots compounded, both process not code:

1. **A no-op oneshot exits `0`.** systemd's success signal is identical whether `main()`
   ran or did nothing, so there was no failure to read — the suspect component was silent.
2. **The debugging theorized about code that never executed.** It chased systemd
   ordering / `--no-block` / race theories for `dispatch_boot`'s `systemctl start` while
   that function was never reached. That persisted because (a) the journal wasn't in the
   agent's hands — feedback was human-mediated copy-paste round-trips (slow, line-wrap-
   mangled, sometimes run on the Mac by accident; see
   `developer-experience/agent-drives-the-pi-directly-over-ssh.md`), and (b) the session
   was at the edge of its context window, so the agent kept re-deriving from its own
   earlier (wrong) systemd theories instead of doing the cheap "did `main()` even run?"
   check. The bug only fell once passwordless SSH put `journalctl` directly in the
   agent's hands.

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

- **Close the class, not just the instance — smoke-test every entrypoint.** Each of the
  four uncovered `ExecStart` entrypoints in the audit table (`sunset_cam.supervisor`,
  `sunset_cam.main`, `scripts/run-setup-server.py`, `scripts/run-setup-app.py`) needs a
  test that exercises the *real* invocation path against a realistic config with IO
  mocked at the edges — not just the injected-deps inner function. The bug class is
  "the wired-up `main()` was never run in a test," and it covers missing guards, wrong
  loaders (`load_config` vs `load_identity`), and dropped config fields (`hardware_id`)
  alike. A `main()` smoke test that asserts "register + first heartbeat were attempted"
  would have caught all three sibling bugs in CI instead of on a Pi.
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
