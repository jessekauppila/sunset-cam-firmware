import { useState, useMemo, useEffect, useRef } from "react";

/* ============================== DOMAIN MATH ===============================
   Real computations per the prototyping brief — copy-ready for firmware.   */

const rad = (d) => (d * Math.PI) / 180;
const deg = (r) => (r * 180) / Math.PI;
const angDiff = (a, b) => ((a - b + 540) % 360) - 180;

function julianDay(date) {
  let y = date.getUTCFullYear(), m = date.getUTCMonth() + 1, d = date.getUTCDate();
  if (m <= 2) { y -= 1; m += 12; }
  const a = Math.floor(y / 100), b = 2 - a + Math.floor(a / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + b - 1524.5;
}
function solarDeclination(date) {
  const n = julianDay(date) + 0.5 - 2451545.0;
  const g = rad((357.528 + 0.9856003 * n) % 360);
  const lam = rad((280.46 + 0.9856474 * n + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) % 360);
  const eps = rad(23.439 - 0.0000004 * n);
  return deg(Math.asin(Math.sin(eps) * Math.sin(lam)));
}
function sunsetAzimuth(latDeg, date) {
  const decl = rad(solarDeclination(date));
  let cosA = Math.sin(decl) / Math.cos(rad(latDeg));
  cosA = Math.max(-1, Math.min(1, cosA));
  return (360 - deg(Math.acos(cosA))) % 360;
}
const sunriseAzimuth = (lat, date) => (360 - sunsetAzimuth(lat, date)) % 360;
const eventAz = (lat, date, facing) =>
  facing === "east" ? sunriseAzimuth(lat, date) : sunsetAzimuth(lat, date);

function arcAnchors(lat, Y, facing) {
  return {
    jun: eventAz(lat, new Date(Date.UTC(Y, 5, 21)), facing),
    equinox: eventAz(lat, new Date(Date.UTC(Y, 2, 20)), facing),
    dec: eventAz(lat, new Date(Date.UTC(Y, 11, 21)), facing),
    today: eventAz(lat, new Date(), facing),
  };
}
const HFOV = { wide: 120, standard: 66 };
const arcSpan = (a) => Math.abs(angDiff(a.jun, a.dec));
const recommendLens = (a) => (arcSpan(a) > HFOV.standard ? "wide" : "standard");
// v19 bracket ladder: discrete azimuth wedges, horizontal only.
// CONFIRMED so far: 0–20° in 5° steps. OPEN: the brackets could physically go
// larger — possibly to 45°. WEDGE_MAX is the one knob to change if/when the
// range is decided; the ladder regenerates from it.
const WEDGE_STEP = 5;
const WEDGE_MAX = 20;                  // ← bump to 45 if the larger wedges ship
const WEDGE_ANGLES = Array.from({ length: WEDGE_MAX / WEDGE_STEP + 1 }, (_, i) => i * WEDGE_STEP);
const snapWedge = (deg) => {
  const mag = Math.min(WEDGE_MAX, Math.abs(deg));
  const a = WEDGE_ANGLES.reduce((p, c) => (Math.abs(c - mag) < Math.abs(p - mag) ? c : p), 0);
  return { angle: a, sign: deg < 0 ? -1 : 1 }; // sign drives flip direction
};

// Coverage is intentionally NOT computed here. Per v19 the sunsets/year figure
// was never a real calculation; it must come from (window offset, wedge angle,
// true 120° FOV, lens-hole vignetting) on the bracket side. UI shows it as TBD.
const toTrue = (mag, decl) => (mag + decl + 360) % 360;
const azToX = (az, centerAz, fovDeg, width) =>
  width * (0.5 + angDiff(az, centerAz) / fovDeg);
const bracketHorizontalWedge = (windowNormalAz, targetAz) => angDiff(targetAz, windowNormalAz);
// NOTE: there is no ±65° bracket limit. The old "viability" gate was the lens
// half-FOV conflated with a bracket angle (v19 correction). The real ceiling is
// WEDGE_MAX (currently 20°, may extend to ~45°); past it the window is a poor
// fit, surfaced as residual rather than a hard block.

const WINDS = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
const compassName = (az) => WINDS[Math.round((((az % 360) + 360) % 360) / 22.5) % 16];

/* =============================== UI PIECES =============================== */

const C = {
  amber: "#ffcc66", amber2: "#ffd088", amber3: "#ffaa55", sun: "#ffd54a",
  goodBg: "#1f4a24", goodFg: "#a5e0aa", badBg: "#5a1f1f", badFg: "#f0b0b0",
  warnBg: "#4a3a1c", btn: "#4a7acc", link: "#9cc4ff",
  glass: "#3a4a60", room: "#1c1812", outdoors: "#0a1420",
};

function Chip({ tone = "info", children }) {
  const s = {
    info: { background: "#181818", border: "1px solid #2a2a2a", color: C.amber2 },
    dark: { background: "#181818", border: "1px solid #2a2a2a", color: "#ddd" },
    good: { background: C.goodBg, color: C.goodFg },
    bad: { background: C.badBg, color: C.badFg },
    warn: { background: C.warnBg, color: C.amber2 },
  }[tone];
  return <div className="rounded-lg px-3 py-2 text-sm mt-2" style={s}>{children}</div>;
}
function Btn({ children, ghost, ...p }) {
  return (
    <button {...p}
      className={"w-full mt-3 rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-40 " + (ghost ? "border" : "")}
      style={ghost ? { color: C.link, borderColor: "#2a3a55", background: "transparent" }
                   : { background: C.btn, color: "#fff" }}>
      {children}
    </button>
  );
}
function Label({ children }) {
  return <div className="text-xs uppercase tracking-widest text-neutral-500 mt-4 mb-1">{children}</div>;
}
function Why({ children }) {
  return (
    <p className="rounded-lg px-3 py-2.5 text-sm leading-relaxed mb-3"
       style={{ background: "#13161c", border: "1px solid #232a36", color: "#99aabb" }}>
      {children}
    </p>
  );
}

/* Shared frame for top-down diagrams: OUTSIDE up, glass line, ROOM down. */
function InsideOutFrame({ W = 360, H, glassY, children, caption }) {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg block mt-2" style={{ background: "#181818" }}>
      <rect x="0" y="0" width={W} height={glassY} fill={C.outdoors} opacity=".55" />
      <rect x="0" y={glassY} width={W} height={H - glassY} fill={C.room} opacity=".5" />
      <line x1="26" y1={glassY} x2={W - 26} y2={glassY} stroke={C.glass} strokeWidth="5" />
      <text x="8" y="14" fill="#56708a" fontSize="9">OUTSIDE</text>
      <text x="8" y={H - 8} fill="#8a7a56" fontSize="9">INSIDE (the room)</text>
      {caption && <text x={W / 2} y={H - 8} fill="#999" fontSize="9" textAnchor="middle">{caption}</text>}
      {children}
    </svg>
  );
}

/* ANIMATION 1 — place the phone flat on the glass (top-down). */
function PlacePhoneAnim() {
  const glassY = 52;
  return (
    <InsideOutFrame H={150} glassY={glassY} caption="press the phone flat — screen toward you">
      <g className="anim-place" style={{ transformBox: "fill-box", transformOrigin: "center" }}>
        <rect x="130" y={glassY + 3} width="100" height="16" rx="4" fill="#0e1622" stroke={C.btn} strokeWidth="1.5" />
        <line x1="138" y1={glassY + 11} x2="158" y2={glassY + 11} stroke={C.link} strokeWidth="2" opacity=".5" />
        <line x1="180" y1={glassY - 2} x2="180" y2="20" stroke={C.amber} strokeWidth="2" strokeDasharray="3 4" />
      </g>
      <path d="M 254 110 q 26 -26 6 -48" fill="none" stroke="#888" strokeWidth="1.5" strokeDasharray="3 3" />
      <path d="M 258 64 l 2 10 -10 -2 z" fill="#888" />
      <text x="262" y="116" fill="#888" fontSize="9">flatten against the glass</text>
      <text x="186" y="32" fill={C.amber2} fontSize="9">back camera looks out → reads the window's facing</text>
    </InsideOutFrame>
  );
}

/* ANIMATION 2 — hinge like a door, INTO the room.
   DEMO mode: a rAF tween loops the move, alternating which edge is hinged.
   LIVE mode: as soon as the phone actually moves (hinge slider here; real
   deviceorientation on a phone), the same diagram becomes an instrument —
   the phone graphic tracks your real opening angle, the sun sits at your
   real wedge, and lining them up is the lock. */
function HingeAnim({ wedgeDeg, eventLabel, liveOpenDeg, aligned }) {
  const [mode, setMode] = useState("demo");
  const [demo, setDemo] = useState({ side: "left", ang: 0 });
  const baseline = useRef(null);

  // Hand off from demo to live the moment real movement appears.
  useEffect(() => {
    if (baseline.current === null) { baseline.current = liveOpenDeg; return; }
    if (mode === "demo" && Math.abs(liveOpenDeg - baseline.current) > 3) setMode("live");
  }, [liveOpenDeg, mode]);

  const demoMax = Math.min(38, Math.max(12, Math.abs(wedgeDeg)));
  useEffect(() => {
    if (mode !== "demo") return;
    const reduce = typeof window !== "undefined" && window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setDemo({ side: "left", ang: demoMax });
      const t = setInterval(() =>
        setDemo((d) => ({ side: d.side === "left" ? "right" : "left", ang: demoMax })), 4400);
      return () => clearInterval(t);
    }
    let raf; const t0 = performance.now();
    const ease = (t) => t * t * (3 - 2 * t);
    const loop = (t) => {
      const P = 4200, el = t - t0, k = (el % P) / P;
      const side = Math.floor(el / P) % 2 ? "right" : "left";
      const f = k < 0.45 ? ease(k / 0.45) : k < 0.6 ? 1 : 1 - ease((k - 0.6) / 0.4);
      setDemo({ side, ang: f * demoMax });
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [mode, demoMax]);

  const live = mode === "live";
  const side = live ? (wedgeDeg >= 0 ? "left" : "right") : demo.side;
  const L = side === "left", sgn = L ? 1 : -1;
  const sunAng = live ? Math.min(45, Math.max(4, Math.abs(wedgeDeg))) : demoMax;
  const rawOpen = wedgeDeg >= 0 ? liveOpenDeg : -liveOpenDeg; // toward the sun = +
  const ang = live ? Math.min(52, Math.max(0, rawOpen)) : demo.ang;
  const wrongWay = live && rawOpen < -3;

  const W = 360, H = 196, glassY = 78;
  const hx = L ? 112 : 248, hy = glassY + 10;
  const sc = Math.cos(rad(sunAng)), ss = Math.sin(rad(sunAng));
  const sun = { x: hx + sgn * (54 * sc + 74 * ss), y: hy + (54 * ss - 74 * sc) };
  const arcEnd = { x: hx + sgn * 46 * Math.cos(rad(ang)), y: hy + 46 * Math.sin(rad(ang)) };
  const lit = live && aligned;

  return (
    <InsideOutFrame
      H={H} glassY={glassY}
      caption={
        live
          ? (lit ? "✓ lined up — lock the angle below"
             : wrongWay ? "hinging the wrong way — swing toward the sun"
             : `live — opened ${Math.max(0, rawOpen).toFixed(0)}° of ${Math.abs(wedgeDeg).toFixed(0)}°`)
          : (L ? "sun to the right → hinge the LEFT edge, swing the right edge into the room"
               : "sun to the left → hinge the RIGHT edge, swing the left edge into the room")}>
      <text x={W / 2} y="14" fill={live ? C.goodFg : "#888"} fontSize="9" textAnchor="middle">
        {live ? "LIVE — your phone is driving this" : "demo — move the phone to take over"}
      </text>

      {/* the target: a sun, not a line */}
      <circle cx={sun.x} cy={sun.y} r="11" fill={C.sun}
              stroke={lit ? C.goodFg : "none"} strokeWidth="3" />
      <text x={sun.x - sgn * 16} y={sun.y + 3} fill={lit ? C.goodFg : C.amber2} fontSize="9"
            textAnchor={L ? "end" : "start"}>{eventLabel}{lit ? " ✓" : ""}</text>

      {/* the phone + its rigid aim arrow, rotating about the hinge */}
      <g transform={`rotate(${sgn * ang} ${hx} ${hy})`}>
        <rect x={L ? hx - 2 : hx - 110} y={glassY + 4} width="112" height="15" rx="4"
              fill="#0e1622" stroke={C.btn} strokeWidth="1.5" />
        <line x1={hx + sgn * 54} y1={glassY + 2} x2={hx + sgn * 54} y2="14"
              stroke={lit ? C.goodFg : C.amber} strokeWidth="2" />
        <path d={`M ${hx + sgn * 54} 8 l 5 11 -10 0 z`} fill={lit ? C.goodFg : C.amber} />
      </g>

      {/* hinge marker + the swept angle */}
      <circle cx={hx} cy={hy} r="4.5" fill="#fff" />
      <text x={hx} y={hy + 22} fill="#ccc" fontSize="9" textAnchor="middle">pivot</text>
      <path d={`M ${hx + sgn * 46} ${hy} A 46 46 0 0 ${L ? 1 : 0} ${arcEnd.x} ${arcEnd.y}`}
            fill="none" stroke="#888" strokeWidth="1" strokeDasharray="2 3" />
      <text x={hx + sgn * 62} y={hy + 30} fill={C.amber} fontSize="11" textAnchor="middle"
            style={{ fontVariantNumeric: "tabular-nums" }}>{Math.round(ang)}°</text>
      <text x={W - 8} y="28" fill="#888" fontSize="9" textAnchor="end"
            style={{ fontVariantNumeric: "tabular-nums" }}>
        {live ? `target: ${Math.abs(wedgeDeg).toFixed(0)}°` : `your swing: ${Math.abs(wedgeDeg).toFixed(0)}°`}
      </text>
    </InsideOutFrame>
  );
}

/* SIGNATURE — top-down wedge: camera INSIDE, looking out through the glass. */
function WedgeDiagram({ normalAz, aimAz, hfov, arc, camFrac }) {
  const W = 360, H = 190, glassY = 132;
  const glassL = 50, glassR = 310;
  const cx = glassL + (glassR - glassL) * camFrac, cy = glassY + 14;
  const pt = (relDeg, len) => [cx + len * Math.sin(rad(relDeg)), cy - len * Math.cos(rad(relDeg))];
  const wedge = angDiff(aimAz, normalAz);
  const [nx, ny] = pt(0, 112);
  const [tx, ty] = pt(wedge, 112);
  const [e1x, e1y] = pt(wedge - hfov / 2, 132);
  const [e2x, e2y] = pt(wedge + hfov / 2, 132);
  const [jx, jy] = pt(angDiff(arc.jun, normalAz), 122);
  const [dx2, dy2] = pt(angDiff(arc.dec, normalAz), 122);
  const arcR = 62;
  const a0 = Math.min(0, wedge), a1 = Math.max(0, wedge);
  const arcPath = `M ${pt(a0, arcR)} A ${arcR} ${arcR} 0 0 1 ${pt(a1, arcR)}`;
  return (
    <InsideOutFrame H={H} glassY={glassY}>
      <path d={`M ${cx} ${cy} L ${e1x} ${e1y} L ${e2x} ${e2y} Z`} fill="rgba(255,204,102,.10)" />
      <line x1={cx} y1={cy} x2={jx} y2={jy} stroke={C.amber3} strokeWidth="1" strokeDasharray="4 4" opacity=".6" />
      <line x1={cx} y1={cy} x2={dx2} y2={dy2} stroke={C.amber3} strokeWidth="1" strokeDasharray="4 4" opacity=".6" />
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#8899aa" strokeWidth="1.5" strokeDasharray="5 4" />
      <text x={nx} y={ny - 4} fill="#8899aa" fontSize="9" textAnchor="middle">window normal</text>
      <line x1={cx} y1={cy} x2={tx} y2={ty} stroke={C.amber2} strokeWidth="2.5" />
      <text x={tx} y={ty - 4} fill={C.amber2} fontSize="9" textAnchor="middle">bracket aim</text>
      <path d={arcPath} fill="none" stroke={C.amber} strokeWidth="2" />
      <text x={pt(wedge / 2, arcR + 14)[0]} y={pt(wedge / 2, arcR + 14)[1]} fill={C.amber}
            fontSize="12" textAnchor="middle" style={{ fontVariantNumeric: "tabular-nums" }}>
        {Math.abs(wedge).toFixed(0)}°
      </text>
      <path d={`M ${cx - 9} ${cy + 9} L ${cx + 9} ${cy + 9} L ${cx + 9 - 14 * Math.sin(rad(wedge))} ${cy - 4} Z`}
            fill="#2a2f3a" stroke="#555" strokeWidth="1" />
      <circle cx={cx} cy={cy} r="4.5" fill={C.sun} />
      <text x={cx} y={cy + 26} fill={C.sun} fontSize="9" textAnchor="middle">case on its wedge, inside the glass</text>
    </InsideOutFrame>
  );
}

/* Bracket placeholder: a wedge (smaller than the box) sits between glass and
   case; the case is rotated off the glass by the wedge angle; the camera peeks
   out one face. Final art comes from the bracket-design chat. */
function WedgeCaseBracket({ wedge }) {
  const W = 360, H = 150;
  // ---- plan view (left): glass, wedge, rotated case ----
  const gx = 40, gTop = 24, gBot = 126;          // glass line (vertical)
  const a = rad(Math.min(42, Math.abs(wedge)));
  const cx = gx + 16, cy = 75;                    // case near-corner pivot-ish
  const bw = 64, bh = 46;                         // box footprint
  // box corners rotated by wedge about the glass-side edge
  const rot = (px, py) => [
    cx + (px) * Math.cos(a) - (py) * Math.sin(a),
    cy + (px) * Math.sin(a) + (py) * Math.cos(a),
  ];
  const c1 = rot(0, -bh / 2), c2 = rot(bw, -bh / 2), c3 = rot(bw, bh / 2), c4 = rot(0, bh / 2);
  const boxPts = [c1, c2, c3, c4].map((p) => p.join(",")).join(" ");
  const wedgeTip = rot(0, bh / 2);                // thin end of wedge
  const lensMid = rot(bw, 0);
  return (
    <div className="rounded-lg p-3 mt-2" style={{ border: "1px dashed #555", background: "#141414" }}>
      <div className="text-xs text-neutral-500 mb-1">
        bracket concept — PLACEHOLDER (final renders from the bracket-design chat)
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full block">
        {/* plan view */}
        <text x={gx + 4} y="16" fill="#888" fontSize="9">plan view (looking down)</text>
        <line x1={gx} y1={gTop} x2={gx} y2={gBot} stroke={C.glass} strokeWidth="5" />
        <text x={gx - 6} y={gBot + 12} fill="#667" fontSize="9" textAnchor="middle">glass</text>
        {/* wedge: thin against glass, thick where the box swings off */}
        <polygon points={`${gx},${cy - bh / 2} ${gx},${cy + bh / 2} ${c4[0]},${c4[1]} ${c1[0]},${c1[1]}`}
                 fill="#2a2f3a" stroke="#557" strokeWidth="1" />
        <text x={gx + 14} y={cy + 2} fill={C.amber} fontSize="10"
              style={{ fontVariantNumeric: "tabular-nums" }}>{Math.abs(wedge).toFixed(0)}°</text>
        {/* the case (box), rotated by the wedge */}
        <polygon points={boxPts} fill="#181818" stroke="#667" strokeWidth="1.5" />
        {/* lens peeking out the far face */}
        <circle cx={lensMid[0]} cy={lensMid[1]} r="5" fill="#0e1622" stroke={C.amber3} strokeWidth="2.5" />
        <line x1={lensMid[0]} y1={lensMid[1]}
              x2={lensMid[0] + 30 * Math.cos(a - Math.PI / 2 + Math.PI)} 
              y2={lensMid[1] + 30 * Math.sin(a - Math.PI / 2 + Math.PI)}
              stroke={C.amber2} strokeWidth="1.5" strokeDasharray="3 3" opacity=".6" />
        <text x={c2[0] + 6} y={c2[1]} fill="#888" fontSize="9">case (Pi + camera)</text>
        <text x={lensMid[0] + 8} y={lensMid[1] + 14} fill={C.amber3} fontSize="8">lens peeks out</text>

        {/* side view (right): camera fixed level — sunsets are at the horizon */}
        <text x="226" y="16" fill="#888" fontSize="9">side view</text>
        <line x1="222" y1="24" x2="222" y2="120" stroke={C.glass} strokeWidth="5" />
        <text x="216" y="132" fill="#667" fontSize="9" textAnchor="end">glass</text>
        <g>
          <polygon points="226,58 226,90 250,84 250,64" fill="#2a2f3a" stroke="#557" />
          <rect x="250" y="52" width="56" height="44" rx="4" fill="#181818" stroke="#667" strokeWidth="1.5" />
          <circle cx="306" cy="74" r="5" fill="#0e1622" stroke={C.amber3} strokeWidth="2.5" />
        </g>
        <text x="258" y="118" fill="#888" fontSize="8">wedge between glass &amp; case</text>
        <text x="258" y="40" fill={C.amber} fontSize="9">level — no vertical tilt</text>
      </svg>
    </div>
  );
}

/* Final mount picture — side view, hardware unambiguously in the room. */
function MountDiagram({ wedge }) {
  const W = 360, H = 180, glassX = 150, horizon = 86;
  const camX = glassX + 36, camY = horizon;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg block mt-2" style={{ background: "#181818" }}>
      <rect x="0" y="0" width={glassX} height={H} fill={C.outdoors} />
      <rect x="0" y={horizon + 18} width={glassX} height={H - horizon - 18} fill="#141a14" />
      <line x1="0" y1={horizon + 18} x2={glassX} y2={horizon + 18} stroke="#2e3a2e" strokeWidth="1.5" />
      <circle cx="46" cy="40" r="12" fill={C.sun} />
      <rect x={glassX} y="0" width={W - glassX} height={H} fill={C.room} opacity=".6" />
      <line x1={glassX} y1="6" x2={glassX} y2={H - 24} stroke={C.glass} strokeWidth="6" />
      <rect x={glassX - 4} y={H - 24} width={W - glassX + 4} height="10" fill="#3a3025" />
      <text x="8" y="14" fill="#56708a" fontSize="9">OUTSIDE</text>
      <text x={W - 8} y="14" fill="#8a7a56" fontSize="9" textAnchor="end">INSIDE (the room)</text>
      <text x={W - 8} y={H - 6} fill="#665544" fontSize="9" textAnchor="end">window sill</text>
      {/* wedge sits between glass and case; case holds Pi+camera, lens out the front */}
      <path d={`M ${glassX + 3} ${camY + 20} L ${glassX + 22} ${camY + 20} L ${glassX + 3} ${camY - 4} Z`}
            fill="#2a2f3a" stroke="#557" />
      <g>
        <rect x={camX - 4} y={camY - 12} width="46" height="36" rx="4" fill="#181818" stroke="#667" strokeWidth="1.5" />
        <circle cx={camX - 6} cy={camY + 6} r="4" fill="#0e1622" stroke={C.amber3} strokeWidth="2.5" />
      </g>
      <text x={camX + 48} y={camY + 2} fill="#888" fontSize="9">case: Pi + camera</text>
      <text x={camX + 48} y={camY + 16} fill="#666" fontSize="8">wedge {Math.abs(wedge)}° (into the page)</text>
      <line x1={camX - 8} y1={camY + 6} x2={camX - 148} y2={camY + 6}
            stroke={C.amber2} strokeWidth="2" strokeDasharray="6 5" />
      <text x="60" y={horizon - 8} fill={C.amber2} fontSize="9">view through the glass · level at the horizon</text>
    </svg>
  );
}

function SkyView({ centerAz, fov, arc, showToday, highlightLock, label }) {
  const W = 360, H = 190, horizon = 128;
  const items = [
    ["Jun", arc.jun, C.amber3, "6 5"],
    ["Equinox", arc.equinox, C.amber2, null],
    ["Dec", arc.dec, C.amber3, "6 5"],
    ...(showToday ? [["today", arc.today, C.sun, "2 4"]] : []),
  ];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg block" style={{ background: C.outdoors }}>
      <rect x="0" y={horizon} width={W} height={H - horizon} fill="#141a14" />
      <line x1="0" y1={horizon} x2={W} y2={horizon} stroke="#2e3a2e" strokeWidth="1.5" />
      <line x1={W / 2} y1="0" x2={W / 2} y2={H} stroke={highlightLock ? C.goodFg : "rgba(255,255,255,.3)"}
            strokeWidth={highlightLock ? 2 : 1.5} strokeDasharray="4 5" />
      {items.map(([name, az, color, dash]) => {
        const x = azToX(az, centerAz, fov, W);
        if (x < -20 || x > W + 20) return null;
        return (
          <g key={name}>
            <line x1={x} y1="14" x2={x} y2={H - 8} stroke={color}
                  strokeWidth={name === "Equinox" ? 2.5 : 1.8} strokeDasharray={dash || "none"} />
            <text x={x + 4} y="24" fill={color} fontSize="10">{name}</text>
          </g>
        );
      })}
      <text x="6" y={H - 6} fill="rgba(255,255,255,.4)" fontSize="9">{label}</text>
      <text x={W - 6} y={H - 6} fill="rgba(255,255,255,.5)" fontSize="10" textAnchor="end"
            style={{ fontVariantNumeric: "tabular-nums" }}>heading {Math.round(centerAz)}°</text>
    </svg>
  );
}

function Slider({ label, value, set, min, max, step = 1, unit = "°" }) {
  return (
    <label className="block text-xs text-neutral-400 mt-2">
      <span className="flex justify-between">
        <span>{label}</span>
        <span style={{ fontVariantNumeric: "tabular-nums", color: C.amber2 }}>{value}{unit}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value}
             onChange={(e) => set(+e.target.value)} className="w-full" />
    </label>
  );
}

/* ================================== APP ================================== */

const STEPS = 6;

export default function WindowBracketPrototype() {
  const Y = new Date().getUTCFullYear();
  const [step, setStep] = useState(1);
  const [facing, setFacing] = useState(null);
  const [confirmed, setConfirmed] = useState(false);

  // Simulation panel
  const [lat, setLat] = useState(48.75);
  const [windowMag, setWindowMag] = useState(262);
  const [hingeMag, setHingeMag] = useState(250);
  const [decl, setDecl] = useState(15.3);
  const [lensChoice, setLensChoice] = useState("auto");
  const [showToday, setShowToday] = useState(true);

  const v = facing === "east"
    ? { verb: "rises", event: "sunrise", plural: "sunrises" }
    : { verb: "sets", event: "sunset", plural: "sunsets" };

  const M = useMemo(() => {
    if (!facing) return null;
    const arc = arcAnchors(lat, Y, facing);
    const span = arcSpan(arc);
    const lens = lensChoice === "auto" ? recommendLens(arc) : lensChoice;
    const hfov = HFOV[lens];
    const normalTrue = toTrue(windowMag, decl);
    const targetAz = arc.equinox;
    const wedge = bracketHorizontalWedge(normalTrue, targetAz); // signed, ideal
    // Snap to the manufactured ladder; the lens FOV + sun self-refine absorb the rest.
    const { angle, sign } = snapWedge(wedge);
    const signedWedge = angle * sign;
    const residual = wedge - signedWedge;
    const aimAz = (normalTrue + signedWedge + 360) % 360;
    // Offset of the window from the event's due axis (the input that picks the wedge).
    const offset = wedge; // toward/away from due W(270)/E(90); same number, named for the contract
    const offsetSide = Math.abs(offset) < 0.5 ? null
      : (facing === "west" ? (offset >= 0 ? "north" : "south")
                           : (offset >= 0 ? "south" : "north"));
    const poorFit = Math.abs(wedge) > WEDGE_MAX + 2; // past the ladder → flag, don't block
    return { arc, span, lens, hfov, normalTrue, targetAz, wedge, angle, sign, signedWedge,
             residual, aimAz, offset, offsetSide, poorFit };
  }, [facing, lat, Y, lensChoice, windowMag, decl]);

  const hingeTrue = toTrue(hingeMag, decl);
  const hingeDelta = M ? angDiff(M.targetAz, hingeTrue) : 0;
  const aligned = Math.abs(hingeDelta) <= 2;
  const camFrac = M ? 0.5 - Math.max(-0.32, Math.min(0.32, M.signedWedge / 140)) : 0.5;
  // Flip direction: which side the wedge's tall end points. null at 0°.
  const tallSide = M && M.angle !== 0 ? M.offsetSide : null;

  const go = (n) => { setStep(n); if (n <= 5) setConfirmed(false); };

  const payload = M && {
    window_azimuth_offset_deg: +Math.abs(M.offset).toFixed(1),
    window_offset_side: M.offsetSide,
    wedge_angle_deg: M.angle,
    flip_direction: tallSide,           // null at 0° — the mirror-symmetric part
    residual_aim_error_deg: +M.residual.toFixed(1),
    lens: M.lens === "wide" ? "wide_120" : "standard_66",
    material_thickness_mm: 3.0,
  };

  return (
    <div className="min-h-screen flex justify-center"
         style={{ background: "#000", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      <style>{`
        @keyframes wb-place {
          0%   { transform: translate(34px, 52px) rotate(26deg); }
          55%  { transform: translate(0, 0) rotate(0deg); }
          100% { transform: translate(0, 0) rotate(0deg); }
        }
        .anim-place { animation: wb-place 3.4s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .anim-place { animation: none !important; }
        }
      `}</style>
      <div className="w-full max-w-md text-neutral-200">

        <header className="flex justify-between items-center px-4 py-2.5" style={{ background: "#111" }}>
          <div>
            <div className="text-sm font-medium text-white">Fit the bracket</div>
            <div className="text-xs" style={{ color: "#8fd694" }}>● prototype · sensors simulated</div>
          </div>
          <div className="flex gap-1.5">
            {Array.from({ length: STEPS }, (_, i) => i + 1).map((n) => (
              <i key={n} className="w-2 h-2 rounded-full"
                 style={{ background: n < step ? "#265f2c" : n === step ? C.amber : "#333" }} />
            ))}
          </div>
        </header>

        <div className="flex justify-between items-center px-4 pt-3 min-h-8">
          {step > 1 && !confirmed ? (
            <button onClick={() => go(step - 1)} className="text-sm" style={{ color: C.link }}>‹ Back</button>
          ) : <span />}
          <span className="text-xs text-neutral-500">Step {step} of {STEPS}</span>
        </div>

        <div className="px-4 pb-5">

          {/* 1 — facing */}
          {step === 1 && (
            <>
              <h1 className="text-lg font-medium text-white mb-3">Is this a sunrise or sunset camera?</h1>
              {[["east", "Sunrise", "faces east · 365 sunrises/year"],
                ["west", "Sunset", "faces west · 365 sunsets/year"]].map(([f, t, s]) => (
                <button key={f} onClick={() => { setFacing(f); go(2); }}
                        className="block w-full text-left rounded-xl p-3 mb-2 border"
                        style={{ background: "#181818", borderColor: "#2a2a2a" }}>
                  <span className="block font-medium text-white">{t}</span>
                  <span className="block text-sm text-neutral-500">{s}</span>
                </button>
              ))}
            </>
          )}

          {/* 2 — measure */}
          {step === 2 && M && (
            <>
              <h1 className="text-lg font-medium text-white mb-2">Measure the window</h1>
              <Why>Hold your phone flat against the glass, screen toward you. Its back camera
                now looks out the window — so the compass reads the direction this window faces,
                and the tilt sensor reads the slope of the glass.</Why>
              <PlacePhoneAnim />
              <Label>This window</Label>
              <div className="rounded-xl p-3" style={{ background: "#181818", border: "1px solid #2a2a2a" }}>
                <div className="text-xl text-white" style={{ fontVariantNumeric: "tabular-nums" }}>
                  faces <b style={{ color: C.amber2 }}>{compassName(M.normalTrue)} ({Math.round(M.normalTrue)}°)</b>
                </div>
                <div className="text-sm text-neutral-400 mt-1">
                  {M.offsetSide
                    ? <>{Math.abs(M.offset).toFixed(0)}° {M.offsetSide} of due {facing === "west" ? "west" : "east"}</>
                    : <>due {facing === "west" ? "west" : "east"} — dead on</>}
                  {" · "}true north (magnetic {windowMag}° + {decl}° declination)
                </div>
              </div>
              {!M.poorFit ? (
                <Chip tone="good">✓ This window suits a <b>{M.angle}°</b> wedge — the {v.event} arc lands in view</Chip>
              ) : (
                <Chip tone="warn">This window faces {Math.abs(M.offset).toFixed(0)}° off the {v.event},
                  past the {WEDGE_MAX}° wedge ladder. It'll still work, aimed as close as the {WEDGE_MAX}° part allows
                  ({Math.abs(M.residual).toFixed(0)}° short) — a window closer to due {facing === "west" ? "west" : "east"} would frame it better.</Chip>
              )}
              <Btn onClick={() => go(3)}>Capture — phone is flat on the glass</Btn>
            </>
          )}

          {/* 3 — hinge */}
          {step === 3 && M && (
            <>
              <h1 className="text-lg font-medium text-white mb-2">Hinge to the equinox</h1>
              <Why>Keep one edge of the phone on the glass — whichever edge is closer to the sun's
                side — and swing the other edge open <b>into the room</b>, like a door, until the
                <b> Equinox {v.event}</b> centers in the camera view. That swing <i>is</i> the bracket angle.</Why>
              <HingeAnim wedgeDeg={M.wedge} eventLabel={`Equinox ${v.event}`}
                         liveOpenDeg={angDiff(hingeTrue, M.normalTrue)} aligned={aligned} />
              <div className="mt-2">
                <SkyView centerAz={hingeTrue} fov={60} arc={M.arc}
                         showToday={showToday} highlightLock={aligned} label="phone camera · AR (simulated)" />
              </div>
              <Chip tone={aligned ? "good" : "dark"}>
                {aligned
                  ? <>Equinox line centered — opened {Math.abs(M.wedge).toFixed(0)}° from the glass</>
                  : <>swing {hingeDelta > 0 ? "right →" : "← left"} {Math.abs(hingeDelta).toFixed(0)}° more
                      (use the “hinge heading” slider below)</>}
              </Chip>
              <Btn disabled={!aligned} onClick={() => go(4)}>
                {aligned ? "Tap to lock the angle" : "Line up the Equinox line to lock"}
              </Btn>
            </>
          )}

          {/* 4 — bracket spec */}
          {step === 4 && M && (
            <>
              <h1 className="text-lg font-medium text-white mb-2">Your bracket</h1>
              <div className="rounded-xl p-4" style={{ background: "#181818", border: "1px solid #3a5f40" }}>
                <Label>Wedge angle</Label>
                <div className="text-2xl text-white" style={{ fontVariantNumeric: "tabular-nums" }}>
                  <b style={{ color: C.amber }}>{M.angle}°</b>{" "}
                  <span className="text-base text-neutral-300">
                    {M.angle === 0 ? "— flat bracket, faces straight out" : `wedge pair`}
                  </span>
                </div>
                <div className="text-xs text-neutral-500 mt-0.5">
                  window is {Math.abs(M.offset).toFixed(1)}° off due {facing === "west" ? "west" : "east"};
                  nearest part on the {WEDGE_ANGLES.join("/")}° ladder is {M.angle}°
                  {Math.abs(M.residual) >= 0.5
                    ? <> — the {Math.abs(M.residual).toFixed(1)}° leftover is absorbed by the wide lens and the sun's later fine-tune</>
                    : <> — exact, no leftover</>}
                </div>

                <Label>Flip direction</Label>
                <div className="text-xl text-white">
                  {tallSide
                    ? <>tall end toward <b style={{ color: C.amber }}>{tallSide}</b></>
                    : <><b style={{ color: C.amber }}>none</b> <span className="text-sm text-neutral-400">— flat part, symmetric</span></>}
                </div>
                <div className="text-xs text-neutral-500">
                  {tallSide
                    ? `one part per angle; flipping the pair reverses the aim — here, tall end ${tallSide} swings the view ${tallSide}`
                    : "the 0° bracket is flat and mirror-symmetric; orientation doesn't matter"}
                </div>

                <Label>Lens</Label>
                <div className="text-xl text-white">
                  <b style={{ color: C.amber }}>{M.lens === "wide" ? "wide (120°)" : "standard (66°)"}</b>
                </div>
                <div className="text-xs text-neutral-500">
                  the year's {v.event} arc spans {M.span.toFixed(0)}° at this latitude —{" "}
                  {M.span > HFOV.standard ? "needs the wide lens" : "the standard lens covers it"}
                </div>
              </div>

              <WedgeDiagram normalAz={M.normalTrue} aimAz={M.aimAz} hfov={M.hfov}
                            arc={M.arc} camFrac={camFrac} />
              <div className="text-xs text-neutral-500 mt-1">
                The case mounts wherever it sticks on the pane — position isn't critical with the
                wide lens. Dashed rays = Jun and Dec {v.plural}.
              </div>

              <Chip tone="dark">
                Bracket aim {Math.round(M.aimAz)}° (equinox {Math.round(M.targetAz)}°).
                Sunsets-per-year: <b>TBD</b> — computed on the bracket side from offset, wedge,
                true 120° FOV, and lens-hole vignetting.
              </Chip>
              <Btn onClick={() => go(5)}>This is my bracket — assemble it</Btn>
            </>
          )}

          {/* 5 — assemble */}
          {step === 5 && M && (
            <>
              <h1 className="text-lg font-medium text-white mb-2">Assemble the bracket</h1>
              <WedgeCaseBracket wedge={M.angle} />
              <ol className="mt-3 space-y-2 text-sm text-neutral-300 list-decimal list-inside">
                <li>Confirm the Pi camera is on its 4× M2 standoffs in the <b>lid</b>, lens out
                  through the front hole. (Lid-mounted so you can re-open it later.)</li>
                <li>{M.angle === 0
                  ? <>Use the <b style={{ color: C.amber }}>0° flat bracket pair</b> — this window faces
                      straight out, so orientation doesn't matter.</>
                  : <>Take the <b style={{ color: C.amber }}>{M.angle}°</b> wedge pair and install them
                      with the <b>tall end toward {tallSide}</b> — that swings the view {tallSide}.
                      (Flipping the pair reverses the aim.)</>}</li>
                <li>Assemble as normal: brackets into the lid, slide the lid kusabi in from the side,
                  face plate on, face kusabi to lock.</li>
                <li>Press the face kusabi's VHB tape flush to the glass <b>from inside the room</b>.
                  Camera sits level — sunsets are at the horizon, no tilt needed.</li>
              </ol>
              <div className="text-xs text-neutral-600 mt-3">
                Exact parts, cut files (parametric on 3&nbsp;mm material), and case art come from the
                bracket-design work — this screen is the slot they drop into.
              </div>
              <Btn onClick={() => go(6)}>It's mounted — power it on</Btn>
            </>
          )}

          {/* 6 — confirm */}
          {step === 6 && M && (
            <>
              <h1 className="text-lg font-medium text-white mb-2">Confirm the view</h1>
              <Why>The aim is correct by construction — it's baked into the bracket. The live view
                should already show the {v.event} markers over open sky.</Why>
              <MountDiagram wedge={M.angle} />
              <div className="mt-2">
                <SkyView centerAz={M.aimAz} fov={M.hfov} arc={M.arc} showToday={showToday}
                         label="camera live view (simulated)" />
              </div>
              {!confirmed ? (
                <>
                  <Chip tone="info">Do the {v.event} lines sit over open sky, clear of the frame?</Chip>
                  <Btn onClick={() => setConfirmed(true)}>✓ Looks right — record the bracket spec</Btn>
                  <Btn ghost onClick={() => go(4)}>Something's off — back to the bracket</Btn>
                </>
              ) : (
                <>
                  <Chip tone="good">Bracket spec recorded ✓ — provisional aim set</Chip>
                  <Chip tone="dark">The camera fine-tunes itself to ~1° on the next clear {v.event} —
                    including the {Math.abs(M.residual).toFixed(1)}° snap residual.</Chip>
                  <Label>POST /setup/bracket-confirm</Label>
                  <pre className="rounded-lg p-3 text-xs overflow-x-auto"
                       style={{ background: "#0e0e0e", border: "1px solid #2a2a2a", color: "#9cc4ff" }}>
{JSON.stringify(payload, null, 2)}
                  </pre>
                  <Btn ghost onClick={() => { setFacing(null); go(1); }}>Start over</Btn>
                </>
              )}
            </>
          )}
        </div>

        {/* Simulation panel */}
        <div className="mx-4 mb-6 rounded-lg p-3" style={{ border: "1px dashed #444", color: "#888" }}>
          <div className="text-xs mb-1">simulation controls (sensors mocked — flight-simulator style)</div>
          <Slider label="latitude (°N)" value={lat} set={setLat} min={25} max={60} step={0.25} unit="°N" />
          <Slider label="window facing (compass, magnetic)" value={windowMag} set={setWindowMag} min={0} max={359} />
          <Slider label="hinge heading (screen 3)" value={hingeMag} set={setHingeMag} min={0} max={359} />
          <div className="flex gap-4 items-center mt-2 text-xs flex-wrap">
            <label>declination{" "}
              <input type="number" step="0.1" value={decl} onChange={(e) => setDecl(+e.target.value)}
                     className="w-16 rounded px-1 py-0.5 text-neutral-200"
                     style={{ background: "#0e0e0e", border: "1px solid #333" }} />°E
            </label>
            <label>lens{" "}
              <select value={lensChoice} onChange={(e) => setLensChoice(e.target.value)}
                      className="rounded px-1 py-0.5 text-neutral-200"
                      style={{ background: "#0e0e0e", border: "1px solid #333" }}>
                <option value="auto">auto (recommend)</option>
                <option value="wide">wide 102°</option>
                <option value="standard">standard 66°</option>
              </select>
            </label>
            <label><input type="checkbox" checked={showToday}
                          onChange={(e) => setShowToday(e.target.checked)} /> show today's line</label>
          </div>
        </div>
      </div>
    </div>
  );
}
