# Handoff prompt for the onboarding-wizard chat

Paste the block below into the chat/tool where you're building the setup-wizard mockup.
It briefs that chat on the firmware-side decisions that change the wizard.

---

You're designing the **setup/onboarding wizard for a Raspberry Pi "sunset camera."** An
installer scans a QR on the housing and is walked through aiming the camera at the
horizon so it captures sunsets (or sunrises). The wizard you've designed (4 steps:
sunrise/sunset → method → calibrate → confirm) is approved. Here are the firmware
realities and recent decisions you must build to — they change a few things:

**1. The wizard's home is the CLOUD app, served over HTTPS** (not the camera's local
HTTP). This is required because Step 3b (phone AR) needs the phone's camera
(`getUserMedia`) + compass (`DeviceOrientation`), which browsers only expose over
HTTPS. The cloud page relays the camera's preview frames and sends the captured aim down
to the device. Design every step assuming a normal HTTPS web app.

**2. The MPU/gyro is now OPTIONAL — phone onboarding is the PRIMARY path.** The camera's
tilt sensor is no longer assumed to exist. Implications for the wizard:
  - **Phone method (3b) is the recommended default**, not a secondary option. The phone
    (held mated to the housing) supplies BOTH heading (compass) and tilt at capture.
  - **Don't assume an on-device level check.** The old "level the camera" gate came from
    the MPU. With no MPU, there's no live tilt from the device — tilt comes from the
    phone in 3b. So the leveling UI lives in the *phone* method (the phone's own
    accelerometer), not as a device-driven gate.
  - For the **sun method (3a)** and **window method (3c)**: a live on-device level check
    only exists *if* the unit has the optional MPU. Treat it as a progressive
    enhancement — show it when available, don't block on it when not.
  - Soften the **3a copy** from "no leveling required" to "the camera should sit roughly
    at its mounted position."

**3. The aiming heading is TRUE north.** The phone compass gives MAGNETIC north on iOS;
convert before use: `true = magnetic + declination` (compute declination from the
camera's lat/lng — e.g. Bellingham ≈ +15°E).

**4. "Clipped" means the whole-year sunset arc doesn't fit the field of view** (a
`fits=false` flag), NOT "tap near the frame edge." Phrase the clipped/aim-quality
feedback as "this aim won't catch the whole year's sunsets — nudge toward center,"
not "you tapped too near the edge."

**5. The sun self-refines.** Whatever coarse aim the installer sets (phone/manual/window),
the camera improves it to ~1° automatically on the next clear sunset. Lean into this in
the copy — install can be approximate and still end up precise ("we'll fine-tune it
when the sun's out").

**6. The AR seasonal arcs** (Jun solstice / Equinox / Dec solstice sun-set or -rise
lines) are computed from the camera's lat/lng + date as true-north azimuths and pinned
to compass bearings; they slide as the heading changes. For the phone-AR step, compute
them in the cloud (it knows lat/lng/date) and render client-side against the phone's
compass heading. Equinox sets due west (270) / rises due east (90); summer is north of
that, winter south.

Keep your 4-step structure, the design principles (goal-first, one decision per screen,
feedback adjacent to the control, just-in-time prerequisites, recommended-default +
escape hatch, inline error recovery), and the visual language. Just bake in: cloud/HTTPS
home, phone-first / MPU-optional leveling, true-north conversion, fits-based "clipped,"
and the sun-self-refine promise.

When you have the wizard as actual markup/components, hand it back and it'll be wired to
the real endpoints panel-by-panel (the firmware side has a bridge doc mapping every
panel to an endpoint).
