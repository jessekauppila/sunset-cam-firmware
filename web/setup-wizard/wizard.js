// wizard.js — state machine + UI. No fetch() here; all I/O via api.js.
import { createApi } from './api.js';

const api = createApi();
const $ = (id) => document.getElementById(id);
const HFOV_PI = 102;     // TODO: thread config hfov into the page per bridge doc
const HFOV_PHONE = 60;   // assumed phone camera horizontal FOV for AR projection
const UPRIGHT_TOL = 15;  // ±deg for "held upright" hint (never a blocker)

const S = {
  step: 1, facing: null, method: null,
  heading: null, coarse: false,
  declination: 15.3, magHeading: null, phoneTilt: null,
  arcs: null,
};

const VOCAB = {
  east: { dir: 'east', verb: 'rises', event: 'sunrise', plural: 'sunrises',
          azimuth: 90,  label: 'Sunrise (east)' },
  west: { dir: 'west', verb: 'sets',  event: 'sunset',  plural: 'sunsets',
          azimuth: 270, label: 'Sunset (west)' },
};
const MLABEL = { sun: 'the sun', compass: 'your phone',
                 window: 'window placement', manual: 'manual heading' };

if (api.mock) { document.body.classList.add('mock'); api.mountControls($('mockhost')); }
api.getDeclination().then((d) => { S.declination = d; });
$('devchip').textContent = '\u25CF ' + (api.mock ? 'mock device' : api.deviceId);
// TODO(bridge-doc): replace devchip with real device name + connection state.

// ----------------------------------------------------------- navigation --
const NAMES = { 1: 'Step 1 of 4', 2: 'Step 2 of 4',
                3: 'Step 3 of 4 — calibrate', 4: 'Step 4 of 4 — confirm' };

function show(step) {
  S.step = step;
  for (let i = 1; i <= 4; i++) $('step-' + i).hidden = i !== step;
  $('stepname').textContent = NAMES[step];
  $('backbtn').hidden = step === 1;
  [...$('dots').children].forEach((d, i) => {
    d.className = i + 1 < step ? 'done' : i + 1 === step ? 'on' : '';
  });
  if (step !== 3) teardownStep3();
}
function goto(step, push = true) {
  if (push) history.pushState({ step }, '', '#step' + step);
  show(step);
}
window.addEventListener('popstate', (e) => {
  if (S.step === 3 && S.method === 'compass' && compassSubBack()) {
    history.pushState({ step: 3 }, '', '#step3'); return;
  }
  show(e.state?.step ?? 1);
});
history.replaceState({ step: 1 }, '', '#step1');
$('backbtn').onclick = () => {
  if (S.step === 3 && S.method === 'compass' && compassSubBack()) return;
  history.back();
};

// ------------------------------------------------------------ step 1 + 2 --
document.querySelectorAll('.fc').forEach((c) => c.onclick = () => {
  S.facing = c.dataset.facing;
  const v = VOCAB[S.facing];
  document.querySelectorAll('.windir').forEach((e) => e.textContent = v.dir);
  document.querySelectorAll('.wverb').forEach((e) => e.textContent = v.verb);
  document.querySelectorAll('.wevent').forEach((e) => e.textContent = v.event);
  $('winsub').textContent =
    `easiest — needs a ${v.dir}-facing window; the camera fine-tunes itself later`;
  goto(2);
});

// The app is cloud-served HTTPS, so no secure-context gate. Only gate on the
// browser actually lacking the sensors (e.g. a desktop).
if (!api.mock && typeof DeviceOrientationEvent === 'undefined') {
  $('card-compass').disabled = true;
  $('compass-sub').textContent = "this browser can't read a compass — use another method";
}

document.querySelectorAll('.mc').forEach((c) => c.onclick = () => startMethod(c.dataset.method));
$('manlink').onclick = () => startMethod('manual');

function startMethod(m) {
  S.method = m; S.heading = null; S.coarse = false;
  $('aimnext').disabled = true;
  ['sun', 'compass', 'window', 'manual'].forEach((p) => $('p-' + p).hidden = p !== m);
  goto(3);
  if (m === 'sun') startSun();
  if (m === 'compass') compassSub(1);
  if (m === 'window') startWindow();
}

// --------------------------------------------------------- shared polling --
let poll = null;
function startPoll(fn, ms) { stopPoll(); poll = setInterval(fn, ms); }
function stopPoll() { if (poll) clearInterval(poll); poll = null; }

function teardownStep3() {
  stopPoll(); stopAR();
  document.querySelectorAll('.preview img.stream').forEach(detachStream);
}

// -------------------------------------------------------------- preview ---
// Relayed frames behave like MJPEG from the client's side: ONE <img>, src set
// only while visible, cleared on leave, onerror → backoff. If the relay turns
// out to be WS-pushed JPEGs, swap these two functions only.
// Snapshot-refresh: poll a single JPEG (~1.6 fps). Works on iOS Safari, which
// will not render an MJPEG multipart stream in an <img>. Cloud: same loop over
// relayed snapshot frames.
function attachStream(img) {
  const url = api.frameUrl && api.frameUrl();
  if (!url) return;                       // mock / no preview → leave placeholder
  const tick = () => {
    if (!img.isConnected || img.closest('[hidden]')) return;  // stop when hidden
    img.src = url + '?t=' + Date.now();
  };
  tick();
  img._streamTimer = setInterval(tick, 600);
}
function detachStream(img) {
  if (img._streamTimer) { clearInterval(img._streamTimer); img._streamTimer = null; }
  img.onerror = null;
  img.src = '';
}

// ------------------------------------------------------------- 3a: sun ----
// No level gate. If the unit happens to have the optional MPU, show a
// non-blocking level hint (progressive enhancement); detection runs regardless.
let tapMode = false;
function startSun() {
  attachStream(document.querySelector('#prev-sun .stream'));
  const fb = $('sunfb');
  fb.className = 'fb info';
  fb.innerHTML = '<span class="spin"></span> ☀ finding the sun…';
  $('taplink').hidden = true; $('sunlvl').hidden = true; tapMode = false;
  const t0 = Date.now();
  let found = false;
  startPoll(async () => {
    let st; try { st = await api.getState(); } catch { return; }
    if (st.has_mpu && st.roll != null) showLevelHint($('sunlvl'), st);
    if (!found && st.status === 'tracking') {
      found = true;
      mark('sunmark', st.sun_fx, st.sun_fy);
      finishSun(st.heading_deg, st.fits);
      if (!st.has_mpu) stopPoll();
    } else if (!found && Date.now() - t0 > 12000) {
      stopPoll();
      fb.className = 'fb bad';
      fb.textContent = "couldn't find the sun — clouds or glare?";
      $('taplink').hidden = false;
    }
  }, 600);
}
function showLevelHint(el, st) {
  const ok = Math.abs(st.roll + 90) <= UPRIGHT_TOL && Math.abs(st.pitch) <= UPRIGHT_TOL;
  el.hidden = false;
  el.className = ok ? 'fb good slim' : 'fb warn slim';
  el.textContent = ok ? '✓ level' : '⚠ looks tilted — straighten it if you can';
}
$('taplink').onclick = () => {
  tapMode = true;
  const fb = $('sunfb');
  fb.className = 'fb info'; fb.textContent = 'tap the sun in the preview';
};
$('prev-sun').addEventListener('click', async (ev) => {
  if (!tapMode) return;
  const r = ev.currentTarget.getBoundingClientRect();
  const fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
  mark('tapmark', fx, fy);
  const fb = $('sunfb');
  fb.className = 'fb info'; fb.innerHTML = '<span class="spin"></span> capturing…';
  try {
    const res = await api.tapAim(fx, fy);
    finishSun(res.heading_deg, res.fits, true);
  } catch { fb.className = 'fb bad'; fb.textContent = 'capture failed — tap again'; }
});
function finishSun(h, fits, tapped) {
  const fb = $('sunfb');
  if (fits === false) {
    fb.className = 'fb bad';
    fb.textContent = `calibrated ${h}° — ${clippedCopy()}`;
  } else {
    fb.className = 'fb good';
    fb.textContent = `calibrated ${h}° ✓` + (tapped ? ' — re-tap to adjust' : '');
  }
  setHeadingLocal(h, false);
}
function clippedCopy() {
  return `this aim won't catch the whole year's ${VOCAB[S.facing].plural} — nudge toward center`;
}
function mark(id, fx, fy) {
  const m = $(id);
  m.setAttribute('cx', fx * 1600); m.setAttribute('cy', fy * 900);
  m.setAttribute('visibility', 'visible');
}

// --------------------------------------------------------- 3b: phone ------
// PRIMARY method. The phone, mated to the housing, supplies heading AND tilt.
// Leveling UI lives here, from the phone's own sensors — hint, not blocker.
let oriHandler = null, arRAF = null, arTracks = null;
function compassSub(n) {
  ['c1', 'c2', 'c3'].forEach((id, i) => $(id).hidden = i + 1 !== n);
  if (n === 2) startAR(); else stopAR();
  if (n === 3) {
    attachStream(document.querySelector('#prev-verify .stream'));
    drawMarks($('vmarks'), S.heading, HFOV_PI);
    $('c3h').textContent = S.heading;
  }
}
function compassSubBack() {
  if (!$('c3').hidden) { compassSub(2); return true; }
  if (!$('c2').hidden) { compassSub(1); return true; }
  return false;
}

$('c1ok').onclick = async () => {
  // iOS: sensor permission must come from a user gesture — this one.
  try {
    if (typeof DeviceOrientationEvent !== 'undefined'
        && DeviceOrientationEvent.requestPermission) {
      const p = await DeviceOrientationEvent.requestPermission();
      if (p !== 'granted') throw new Error('denied');
    }
  } catch { showCompassFail('motion access was denied'); return; }
  compassSub(2);
};

async function startAR() {
  S.arcs = await api.getArcAzimuths(S.facing);
  if (!api.mock) {
    try {
      const ms = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' } });
      $('arvideo').srcObject = ms; arTracks = ms.getTracks();
    } catch { showCompassFail('camera access was denied'); return; }
    oriHandler = (e) => {
      // iOS Safari: webkitCompassHeading is MAGNETIC north. Backend wants TRUE.
      let m = e.webkitCompassHeading;
      if (m == null && e.absolute && e.alpha != null) m = 360 - e.alpha;
      if (m != null) S.magHeading = m;
      // Portrait upright ⇒ beta ≈ 90. pitch = lean fwd/back, roll = lean sideways.
      if (e.beta != null) S.phoneTilt = { pitch: e.beta - 90, roll: e.gamma || 0 };
    };
    window.addEventListener('deviceorientation', oriHandler);
  }
  const loop = () => {
    const src = api.mock ? api.getMockPhone() : { heading: S.magHeading, tilt: S.phoneTilt };
    if (src.heading != null) {
      const trueH = (src.heading + S.declination + 360) % 360;
      S._liveTrue = trueH; S._liveTilt = src.tilt;
      $('c2cap').textContent = `phone heading ${Math.round(trueH)}° — tap to capture`;
      drawMarks($('armarks'), trueH, HFOV_PHONE);
      updateTiltChip(src.tilt);
    }
    arRAF = requestAnimationFrame(loop);
  };
  loop();
}
function updateTiltChip(t) {
  const el = $('tiltchip');
  if (!t) { el.hidden = true; return; }
  el.hidden = false;
  const ok = Math.abs(t.pitch) <= UPRIGHT_TOL && Math.abs(t.roll) <= UPRIGHT_TOL;
  el.className = ok ? 'fb good slim' : 'fb warn slim';
  el.textContent = ok ? '✓ held upright'
    : '⚠ tilted — straighten the pair if you can (we record the tilt either way)';
}
function stopAR() {
  if (arRAF) cancelAnimationFrame(arRAF); arRAF = null;
  if (oriHandler) window.removeEventListener('deviceorientation', oriHandler);
  oriHandler = null;
  if (arTracks) arTracks.forEach((t) => t.stop());
  arTracks = null;
}

// Project TRUE-north azimuths onto x for a view centered on centerAz.
// v1 = vertical azimuth guides sliding with the heading; full altitude arcs
// are a later enhancement inside this function only.
function drawMarks(g, centerAz, hfov) {
  if (!S.arcs) return;
  const items = [
    ['Jun', S.arcs.jun, 'armark season'],
    ['Equinox', S.arcs.equinox, 'armark equinox'],
    ['Dec', S.arcs.dec, 'armark season'],
    ['today', S.arcs.today, 'armark today'],
  ];
  let out = '';
  for (const [label, az, cls] of items) {
    const d = ((az - centerAz + 540) % 360) - 180;
    if (Math.abs(d) > hfov / 2 + 8) continue;
    const x = 800 + (d / hfov) * 1600;
    out += `<line x1="${x}" y1="80" x2="${x}" y2="860" class="${cls}"/>`
         + `<text x="${x + 12}" y="130" class="arlabel">${label}</text>`;
  }
  g.innerHTML = out;
}

$('c2cap').onclick = () => {
  if (S._liveTrue == null) { showCompassFail('no compass reading yet'); return; }
  S.heading = Math.round(S._liveTrue);
  S._capturedTilt = S._liveTilt || null;
  const fb = $('c2fb');
  fb.hidden = false; fb.className = 'fb good';
  fb.textContent = `captured ${S.heading}° ✓`;
  setTimeout(() => compassSub(3), 400);
};
function showCompassFail(reason) {
  const fb = $('c2fb');
  fb.hidden = false; fb.className = 'fb bad';
  fb.innerHTML = `${reason} — <button class="linkbtn" id="fallman">enter the heading manually</button>`;
  $('fallman').onclick = () => startMethod('manual');
}
$('c3yes').onclick = async () => {
  const fb = $('c3fb');
  fb.className = 'fb info'; fb.innerHTML = '<span class="spin"></span> setting…';
  try {
    const res = await api.setAim({ heading_deg: S.heading, source: 'phone',
                                   tilt: S._capturedTilt });
    if (res.fits === false) {
      fb.className = 'fb bad';
      fb.textContent = `calibrated ${res.heading_deg}° — ${clippedCopy()}`;
    } else {
      fb.className = 'fb good';
      fb.textContent = `calibrated ${res.heading_deg}° ✓ — verified against live view`;
    }
    setHeadingLocal(res.heading_deg, true); // phone aim is coarse; sun refines it
  } catch {
    fb.className = 'fb bad'; fb.textContent = 'setting failed — try again';
  }
};
$('c3no').onclick = () => { $('c2fb').hidden = true; compassSub(2); };

// ----------------------------------------------------------- 3c: window ---
// No blocker. If the unit has the optional MPU, the level line goes live;
// otherwise the instruction stands alone.
function startWindow() {
  attachStream(document.querySelector('#prev-window .stream'));
  $('lvlline').setAttribute('visibility', 'hidden');
  $('wbanner').className = 'fb info';
  $('wbanner').textContent = 'Set it level on the sill — eyeballing it is fine.';
  startPoll(async () => {
    let st; try { st = await api.getState(); } catch { return; }
    if (!st.has_mpu || st.roll == null) { stopPoll(); return; }
    const ok = Math.abs(st.roll + 90) <= UPRIGHT_TOL && Math.abs(st.pitch) <= UPRIGHT_TOL;
    const l = $('lvlline');
    l.setAttribute('visibility', 'visible');
    l.setAttribute('transform', `rotate(${(st.roll + 90).toFixed(1)} 800 450)`);
    l.classList.toggle('good', ok);
    const b = $('wbanner');
    b.className = ok ? 'fb good' : 'fb warn';
    b.textContent = ok ? '✓ Level'
      : '⚠ Looks tilted — the dashed line should sit on the horizon';
  }, 700);
}
$('winok').onclick = async () => {
  const az = VOCAB[S.facing].azimuth;
  const fb = $('winfb');
  fb.hidden = false; fb.className = 'fb info';
  fb.innerHTML = '<span class="spin"></span> setting…';
  try {
    await api.setAim({ heading_deg: az, source: 'window' });
    fb.className = 'fb good';
    fb.textContent = `calibrated ~${az}° (${VOCAB[S.facing].dir}-facing) ✓`;
    setHeadingLocal(az, true);
  } catch { fb.className = 'fb bad'; fb.textContent = 'setting failed — try again'; }
};

// ----------------------------------------------------------- 3d: manual ---
$('manset').onclick = async () => {
  const v = ((Math.round(+$('manin').value) % 360) + 360) % 360;
  const fb = $('manfb');
  fb.hidden = false; fb.className = 'fb info';
  fb.innerHTML = '<span class="spin"></span> setting…';
  try {
    const res = await api.setAim({ heading_deg: v, source: 'manual' });
    if (res.fits === false) {
      fb.className = 'fb bad';
      fb.textContent = `calibrated ${res.heading_deg}° — ${clippedCopy()}`;
    } else {
      fb.className = 'fb good';
      fb.textContent = `calibrated ${res.heading_deg}° ✓`;
    }
    setHeadingLocal(res.heading_deg, true);
  } catch { fb.className = 'fb bad'; fb.textContent = 'setting failed — try again'; }
};

// ------------------------------------------------------------- step 4 -----
function setHeadingLocal(h, coarse) {
  S.heading = h; S.coarse = coarse; $('aimnext').disabled = false;
}
const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
const compass = (az) => COMPASS[Math.round(((az % 360) / 45)) % 8];

$('aimnext').onclick = async () => {
  const v = VOCAB[S.facing];
  $('sumface').textContent = v.label;
  $('summeth').textContent = MLABEL[S.method];
  $('sumhead').textContent = (S.coarse ? '≈ ' : '') + S.heading + '° (' + compass(S.heading) + ')';
  $('sumcoverlbl').textContent = v.plural + ' / year';
  $('sumcover').textContent = '…';
  $('sumnote').hidden = !S.coarse;
  if (S.coarse) $('sumnote').textContent =
    `starting at ≈${S.heading}° — the camera fine-tunes itself to about 1° ` +
    `on the next clear ${v.event}`;
  const rot = $('sumrotate'); rot.hidden = true;
  goto(4);
  // how many sunsets/year this aim catches, and how many more by rotating
  try {
    const cov = await api.getCoverage(S.heading);
    $('sumcover').textContent = '~' + cov.captured;
    const more = cov.captured_at_best - cov.captured;
    rot.hidden = false;
    rot.textContent = more > 5
      ? `↻ rotate toward ${compass(cov.best_center_az)} (${Math.round(cov.best_center_az)}°) ` +
        `to catch ~${cov.captured_at_best} ${v.plural}/year (+${more})`
      : `✓ about the most this spot can catch (${cov.captured} ${v.plural}/year)`;
  } catch { $('sumcover').textContent = '—'; }
};
$('r-face').onclick = () => goto(1);
$('r-meth').onclick = () => goto(2);
$('confirmbtn').onclick = async () => {
  const fb = $('conffb'); const b = $('confirmbtn');
  fb.hidden = false; fb.className = 'fb info';
  fb.innerHTML = '<span class="spin"></span> confirming…';
  b.disabled = true;
  try {
    await api.confirmAim({ heading_deg: S.heading, method: S.method,
                           facing: S.facing, coarse: S.coarse });
    fb.className = 'fb good'; fb.textContent = 'Aim confirmed ✓';
    b.textContent = 'Aim confirmed ✓';
  } catch {
    fb.className = 'fb bad'; fb.textContent = 'confirm failed — try again';
    b.disabled = false;
  }
};
