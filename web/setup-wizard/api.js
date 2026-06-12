// api.js — ALL network access lives here. The wizard's home is the CLOUD app
// (HTTPS): the cloud relays the camera's preview and sends captured aim down
// as set-aim directives. Wiring to real endpoints = reconcile the
// TODO(bridge-doc) markers against the bridge doc, only in this file.
//
// Mock mode: ?mock=1 (or file://). Injects a simulation panel: MPU on/off,
// sun-detection failure, phone heading slider, phone-tilted toggle.

export function createApi() {
  const mock = new URLSearchParams(location.search).has('mock')
    || location.protocol === 'file:';
  return mock ? mockApi() : realApi();
}

// ---------------------------------------------------------------- real ----
function realApi() {
  // WIRED to the firmware-local setup endpoints (/setup/*), served by the Pi's
  // setup server. In the cloud-served deployment these become device-scoped relay
  // routes (/api/devices/{id}/*); only the bodies in this file change, not the wizard.
  // Contract source of truth: docs/superpowers/specs/2026-06-10-setup-wizard-implementation-context.md
  const deviceId = new URLSearchParams(location.search).get('device')
    || (location.pathname.match(/devices\/([^/]+)/) || [])[1]
    || 'local';

  return {
    mock: false,
    deviceId,

    // Pi MJPEG preview (<img>-compatible). Cloud: relayed frames.
    streamUrl: () => '/setup/preview.mjpg',
    // Single-JPEG snapshot for snapshot-refresh previews (iOS can't render MJPEG).
    frameUrl: () => '/setup/frame.jpg',

    // /setup/state.json → normalize firmware field names (roll_deg→roll) to the
    // wizard's shape { status, has_mpu, roll?, pitch?, sun_fx?, sun_fy?, heading_deg?, fits? }.
    async getState() {
      const r = await fetch('/setup/state.json', { cache: 'no-store' });
      if (!r.ok) throw new Error('state ' + r.status);
      const s = await r.json();
      return {
        status: s.status, has_mpu: s.has_mpu,
        roll: s.roll_deg, pitch: s.pitch_deg,
        sun_fx: s.sun_fx, sun_fy: s.sun_fy,
        heading_deg: s.heading_deg, fits: s.fits,
      };
    },

    // Tap-to-calibrate. Firmware accepts the fraction directly. → { heading_deg, fits }.
    async tapAim(fx, fy) {
      return post('/setup/tap', { fx, fy });
    },

    // Set the heading. The phone's tilt rides along on phone-source aims and is
    // recorded (and gated on) when the unit has no MPU.
    // payload: { heading_deg, source:'phone'|'window'|'manual', tilt?:{pitch,roll} }
    async setAim(payload) {
      const body = { heading_deg: payload.heading_deg, source: payload.source };
      if (payload.tilt) { body.roll_deg = payload.tilt.roll; body.pitch_deg = payload.tilt.pitch; }
      return post('/setup/heading', body);
    },

    // Firmware confirms the current anchored aim → { status:'confirmed', placement }.
    async confirmAim(_payload) {
      return post('/setup/confirm', {});
    },

    // Seasonal set/rise azimuths (TRUE north) from the device's lat/lng + date.
    async getArcAzimuths(facing) {
      const r = await fetch('/setup/arc-azimuths?facing=' + facing);
      if (!r.ok) throw new Error('arc-azimuths ' + r.status);
      return r.json();
    },

    // Coverage for a heading: { captured, best_center_az, captured_at_best, fits, ... }.
    async getCoverage(heading) {
      const r = await fetch('/setup/coverage?heading=' + Math.round(heading));
      if (!r.ok) throw new Error('coverage ' + r.status);
      return r.json();
    },

    // No on-device WMM model; the cloud-served deployment computes this from
    // lat/lng. Local fallback (Bellingham-area, +E).
    async getDeclination() {
      return 15.3;
    },
  };

  async function post(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(url + ' ' + r.status);
    return r.json();
  }
}

// ---------------------------------------------------------------- mock ----
function mockApi() {
  const m = {
    hasMpu: false,           // phone-first world: default OFF
    roll: -47, pitch: 3,     // only reported when hasMpu
    detectFail: false,
    phoneHeading: 268,       // magnetic, slider-driven
    phoneTilted: false,
    leveling: null,
  };

  return {
    mock: true,
    deviceId: 'mock-cam',
    streamUrl: () => '', // wizard shows the placeholder sky instead
    frameUrl: () => '',  // mock: no snapshot URL → placeholder sky

    async getState() {
      const st = { status: m.detectFail ? 'idle' : 'tracking', has_mpu: m.hasMpu };
      if (!m.detectFail) {
        st.sun_fx = 0.64; st.sun_fy = 0.28; st.heading_deg = 247; st.fits = true;
      }
      if (m.hasMpu) { st.roll = m.roll; st.pitch = m.pitch; }
      return st;
    },
    async tapAim(fx) {
      await wait(800);
      const h = Math.round((253 + (fx - 0.5) * 102) + 360) % 360;
      return { heading_deg: h, fits: Math.abs(fx - 0.5) <= 0.42 };
    },
    async setAim(p) { await wait(600); return { heading_deg: p.heading_deg, fits: true }; },
    async confirmAim() { await wait(700); return { ok: true }; },
    async getArcAzimuths(facing) {
      const e = facing === 'east' ? 90 : 270;
      return { jun: e + 33, equinox: e, dec: e - 33, today: e - 4 };
    },
    async getCoverage(h) {
      const best = 285, peak = 289;                         // mock: best aim ≈ due west
      const off = Math.min(180, Math.abs(((h - best + 180) % 360) - 180));
      const captured = Math.max(20, Math.round(peak - off * 3.5));
      return { fits: off < 8, captured, best_center_az: best, captured_at_best: peak,
               summer_az: 307, winter_az: 233 };
    },
    async getDeclination() { return 15.3; },

    // mock-only hooks
    getMockPhone() {
      return { heading: m.phoneHeading,
               tilt: m.phoneTilted ? { pitch: 24, roll: -11 } : { pitch: 1, roll: 0 } };
    },

    mountControls(host) {
      const d = document.createElement('div');
      d.className = 'mockpanel';
      d.innerHTML =
        'simulation controls (mock mode only)<br>' +
        '<label><input type="checkbox" id="mk-mpu"> unit has the optional MPU</label> ' +
        '<button id="mk-level" disabled>level the housing</button><br>' +
        '<label><input type="checkbox" id="mk-fail"> sun detection fails</label> ' +
        '<label><input type="checkbox" id="mk-tilt"> phone held tilted</label><br>' +
        '<label>phone heading <input type="range" id="mk-ph" min="180" max="359" value="268"> ' +
        '<span id="mk-phv">268</span>&deg;</label>';
      host.appendChild(d);
      d.querySelector('#mk-mpu').onchange = (e) => {
        m.hasMpu = e.target.checked;
        d.querySelector('#mk-level').disabled = !m.hasMpu;
      };
      d.querySelector('#mk-level').onclick = () => {
        clearInterval(m.leveling);
        m.leveling = setInterval(() => {
          m.roll += (-90 - m.roll) * 0.2; m.pitch *= 0.8;
          if (Math.abs(m.roll + 90) < 0.5) { m.roll = -90; m.pitch = 0; clearInterval(m.leveling); }
        }, 100);
      };
      d.querySelector('#mk-fail').onchange = (e) => { m.detectFail = e.target.checked; };
      d.querySelector('#mk-tilt').onchange = (e) => { m.phoneTilted = e.target.checked; };
      d.querySelector('#mk-ph').oninput = (e) => {
        m.phoneHeading = +e.target.value;
        d.querySelector('#mk-phv').textContent = e.target.value;
      };
    },
  };
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
