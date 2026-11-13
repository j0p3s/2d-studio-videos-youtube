// Deterministic skeletal character rig. No DOM or renderer dependencies.
//
// A character is a bone hierarchy with FIXED lengths. A pose is a flat object of joint ANGLES
// (degrees) plus a root offset; it can never stretch a limb or break an anatomical limit.
// `rigJoints()` solves a pose to the 11 world-space joints the stick/hoodie renderer already
// draws (head, sh, hip, eF, hF, eB, hB, kF, fF, kB, fB), so existing scenes and tools keep
// working while new scenes author motion with bones instead of raw coordinates.
//
// Local space matches rig2d.js: feet on y=0, up is -y, the figure faces +x, height ~240.
//   hip -> spine -> chest -> neck/head      (angles measured from vertical, forward = +x)
//   shoulder -> upper arm -> forearm -> hand (angles from hanging straight down, forward = +x)
//   hip -> thigh -> shin -> ankle            (angles from straight down, forward = +x)
// shoulderX/thighX are swing angles, elbowX/kneeX are flexion (forearm forward / shin backward).
// F = near limb, B = far limb. Arm angles are relative to the chest so arms follow the torso.

const DEG = Math.PI / 180;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const wrap = (d) => { d = (((d + 180) % 360) + 360) % 360 - 180; return d === -180 ? 180 : d; };
const wrapTo = (d, min) => (((d - min) % 360) + 360) % 360 + min;
const up = (a) => [Math.sin(a), -Math.cos(a)];
const dn = (a) => [Math.sin(a), Math.cos(a)];
const along = (p, v, l) => [p[0] + v[0] * l, p[1] + v[1] * l];

export const RIG = Object.freeze({ spine: 36, chest: 38, neck: 34, upperArm: 38, foreArm: 38, thigh: 50, shin: 50, standHeight: 100 });
export const BUILDS = Object.freeze({
  standard: Object.freeze({ legs: 1, arms: 1, torso: 1, neck: 1 }),
  tall: Object.freeze({ legs: 1.1, arms: 1.05, torso: 1.02, neck: 1 }),
  stocky: Object.freeze({ legs: 0.92, arms: 0.96, torso: 1.06, neck: 0.9 }),
  lanky: Object.freeze({ legs: 1.08, arms: 1.12, torso: 0.96, neck: 1.1 }),
});

// name: [default, min, max]  (degrees, except x/lift in rig units)
const CHANNELS = {
  x: [0, -400, 400], lift: [0, -50, 600],
  spine: [0, -60, 80], chest: [0, -45, 60], neck: [5, -70, 70],
  shoulderF: [12, -80, 200], elbowF: [3, -8, 155], shoulderB: [-10, -80, 200], elbowB: [6, -8, 155],
  thighF: [7, -70, 125], kneeF: [10, 0, 150], thighB: [-7, -70, 125], kneeB: [0, 0, 150],
};
export const RIG_CHANNELS = Object.freeze(Object.keys(CHANNELS));

function lengths(build) {
  const b = typeof build === 'string' ? BUILDS[build] : { ...BUILDS.standard, ...(build || {}) };
  if (!b) throw new TypeError(`Unknown rig build '${build}'. Use ${Object.keys(BUILDS).join(', ')}`);
  for (const k of ['legs', 'arms', 'torso', 'neck']) if (!(b[k] > 0 && Number.isFinite(b[k]))) throw new TypeError(`Invalid rig build scale ${k}`);
  return { spine: RIG.spine * b.torso, chest: RIG.chest * b.torso, neck: RIG.neck * b.neck, upperArm: RIG.upperArm * b.arms, foreArm: RIG.foreArm * b.arms, thigh: RIG.thigh * b.legs, shin: RIG.shin * b.legs };
}

export const isRigPose = (p) => !!p && typeof p === 'object' && !Array.isArray(p) && p.rig === 1;
const JOINT_KEYS = ['head', 'sh', 'hip', 'eF', 'hF', 'eB', 'hB', 'kF', 'fF', 'kB', 'fB'];

function normalise(p) {
  if (!p || typeof p !== 'object') throw new TypeError('Rig pose must be an object');
  for (const k of Object.keys(p)) {
    if (k !== 'rig' && k !== 'height' && !(k in CHANNELS)) {
      if (JOINT_KEYS.includes(k)) throw new TypeError(`'${k}' is a joint POSITION, not a rig channel: rig poses are joint ANGLES (${RIG_CHANNELS.join(', ')}). Move a hand or foot with rigReach/rigPlant, and read joint positions from the pose (pose.${k}) or jointWorld(figure,'${k}')`);
      const near = RIG_CHANNELS.filter((c) => c !== 'x' && (k.startsWith(c) || c.startsWith(k) || c.slice(0, -1) === k.slice(0, -1)));
      throw new TypeError(`Unknown rig channel '${k}'.${near.length ? ` Did you mean ${near.map((c) => `'${c}'`).join(' or ')}? (spine, chest and neck have no F/B suffix.)` : ''} Valid: ${RIG_CHANNELS.join(', ')}, height`);
    }
  }
  const n = { rig: 1 };
  for (const [k, [d, lo, hi]] of Object.entries(CHANNELS)) {
    const v = p[k] ?? d;
    if (!Number.isFinite(v)) throw new TypeError(`Rig channel ${k} must be a finite number`);
    n[k] = clamp(v, lo, hi);
  }
  if (p.height != null) {
    if (!Number.isFinite(p.height) || p.height < 0) throw new TypeError('Rig height must be a finite number >= 0');
    n.height = p.height;
  }
  // Read-only solved joints (pose.hF, pose.head, ...) so code written for the old joint-array
  // poses can still read positions. Non-enumerable: spread/copy keeps only the real channels.
  for (const k of JOINT_KEYS) Object.defineProperty(n, k, { enumerable: false, configurable: true, get() { return rigJoints(this)[k]; } });
  return n;
}

function points(n, L, hip) {
  const T1 = n.spine * DEG, T2 = T1 + n.chest * DEG, T3 = T2 + n.neck * DEG;
  const chest = along(hip, up(T1), L.spine), sh = along(chest, up(T2), L.chest), head = along(sh, up(T3), L.neck);
  const out = { head, sh, hip, chest };
  for (const s of ['F', 'B']) {
    const a1 = T2 + n['shoulder' + s] * DEG, e = along(sh, dn(a1), L.upperArm), a2 = a1 + n['elbow' + s] * DEG;
    out['e' + s] = e; out['h' + s] = along(e, dn(a2), L.foreArm);
    const b1 = n['thigh' + s] * DEG, k = along(hip, dn(b1), L.thigh), b2 = b1 - n['knee' + s] * DEG;
    out['k' + s] = k; out['f' + s] = along(k, dn(b2), L.shin);
  }
  return out;
}
const groundHeight = (n, L) => { const q = points(n, L, [0, 0]); return Math.max(q.fF[1], q.fB[1]); };

/** Solve a rig pose to the 11 renderer joints. Limb lengths are exact for any input. */
export function rigJoints(pose, opts = {}) {
  const n = normalise(pose), L = lengths(opts.build);
  const h = n.height ?? groundHeight(n, L);
  const q = points(n, L, [n.x, -(h + n.lift)]);
  return { head: q.head, sh: q.sh, hip: q.hip, eF: q.eF, hF: q.hF, eB: q.eB, hB: q.hB, kF: q.kF, fF: q.fF, kB: q.kB, fB: q.fB };
}
/** Height of the hip above the floor when the lowest foot stands on y=0 (before `lift`). */
export const rigGroundHeight = (pose, opts = {}) => { const n = normalise(pose); return n.height ?? groundHeight(n, lengths(opts.build)); };

const POSE_DEFS = {
  stand: {},
  relaxed: { neck: 4, shoulderF: 17, elbowF: 8, shoulderB: -14, elbowB: 4, thighF: 8, thighB: -9 },
  talk: { neck: 5, shoulderF: 27, elbowF: 98 },
  explain: { neck: 5, shoulderF: 30, elbowF: 100, shoulderB: 21, elbowB: 106 },
  point: { chest: 2, shoulderF: 83, elbowF: 8, shoulderB: -8, elbowB: 6 },
  crossArms: { shoulderF: 22, elbowF: 138, shoulderB: 10, elbowB: 128 },
  handsOnHead: { neck: 0, shoulderF: 150, elbowF: 75, shoulderB: 140, elbowB: 85 },
  cheer: { chest: -4, neck: -2, shoulderF: 165, elbowF: 12, shoulderB: 150, elbowB: 18 },
  shrug: { neck: 8, shoulderF: 14, elbowF: 100, shoulderB: 6, elbowB: 104 },
  think: { spine: 2, neck: 12, shoulderF: 36, elbowF: 150, shoulderB: 14, elbowB: 128 },
  wave: { shoulderF: 140, elbowF: 40, shoulderB: -8, elbowB: 6 },
  slump: { spine: 14, chest: 10, neck: 20, shoulderF: 6, elbowF: 6, shoulderB: -6, elbowB: 8 },
  sit: { spine: 2, thighF: 90, kneeF: 90, thighB: 84, kneeB: 86, shoulderF: 36, elbowF: 60, shoulderB: 26, elbowB: 70 },
  sitSlump: { spine: 16, chest: 12, neck: 22, thighF: 90, kneeF: 90, thighB: 84, kneeB: 86, shoulderF: 10, elbowF: 30, shoulderB: 8, elbowB: 36 },
};
export const RIG_POSE_NAMES = Object.freeze(Object.keys(POSE_DEFS));

function resolve(p) {
  if (typeof p === 'string') {
    if (!(p in POSE_DEFS)) throw new TypeError(`Unknown rig pose '${p}'. Valid: ${RIG_POSE_NAMES.join(', ')}`);
    return normalise(POSE_DEFS[p]);
  }
  return normalise(p || {});
}
/** rigPose('talk'), rigPose({shoulderF:90}), rigPose('sit',{neck:20}) -> a new, validated pose. */
export function rigPose(base = 'stand', overrides = {}) {
  const b = resolve(base);
  return normalise({ ...b, ...overrides });
}

const EASE = {
  linear: (k) => k,
  in: (k) => k * k * k,
  out: (k) => 1 - (1 - k) ** 3,
  inOut: (k) => k * k * (3 - 2 * k),
  back: (k) => { const c = 1.70158, m = k - 1; return 1 + (c + 1) * m ** 3 + c * m * m; },
};
const easeFn = (e) => { const f = typeof e === 'function' ? e : EASE[e]; if (!f) throw new TypeError(`Unknown easing '${e}'. Use ${Object.keys(EASE).join(', ')}`); return f; };

/** Blend two poses by angle (limbs keep their length, unlike lerping joint coordinates). */
export function rigBlend(a, b, k, easing = 'inOut') {
  const A = resolve(a), B = resolve(b), t = easeFn(easing)(clamp(k, 0, 1));
  const out = { rig: 1 };
  for (const key of RIG_CHANNELS) out[key] = A[key] + (B[key] - A[key]) * t;
  if (A.height != null || B.height != null) out.height = (A.height ?? groundHeight(A, lengths())) * (1 - t) + (B.height ?? groundHeight(B, lengths())) * t;
  return normalise(out);
}

/**
 * Keyframe sampler. keys: [[seconds, poseOrName], ...].
 * mode 'smooth' (default) eases continuously between keys; 'hold' keeps each pose and
 * blends into the next over `blend` seconds when its key time is reached.
 */
export function rigSample(keys, t, { mode = 'smooth', ease = 'inOut', blend = 0.35 } = {}) {
  if (!Array.isArray(keys) || !keys.length || !Number.isFinite(t)) throw new TypeError('rigSample needs keys [[t,pose],...] and a finite time');
  const ks = keys.map(([time, p]) => { if (!Number.isFinite(time)) throw new TypeError('Key time must be finite'); return [time, resolve(p)]; }).sort((x, y) => x[0] - y[0]);
  if (mode === 'hold') {
    let cur = ks[0][1];
    for (let i = 1; i < ks.length; i++) {
      if (t < ks[i][0]) break;
      const k = clamp((t - ks[i][0]) / Math.max(1e-6, blend));
      if (k < 1) return rigBlend(cur, ks[i][1], k, ease);
      cur = ks[i][1];
    }
    return normalise(cur);
  }
  if (t <= ks[0][0]) return normalise(ks[0][1]);
  for (let i = 0; i < ks.length - 1; i++) {
    const [t0, p0] = ks[i], [t1, p1] = ks[i + 1];
    if (t <= t1) return rigBlend(p0, p1, t1 > t0 ? (t - t0) / (t1 - t0) : 1, ease);
  }
  return normalise(ks[ks.length - 1][1]);
}

/** Add delta channels (e.g. from rigIdle) on top of a pose; result stays within joint limits. */
export function rigAdd(base, delta, weight = 1) {
  const b = resolve(base), out = { ...b };
  for (const k of RIG_CHANNELS) if (delta?.[k] != null) out[k] = b[k] + weight * delta[k];
  return normalise(out);
}
/** Small idle life: breathing and sway as additive channels. rigAdd(pose, rigIdle(t)). */
export function rigIdle(t, { amount = 1, seed = 0, rate = 1 } = {}) {
  const breath = Math.sin(t * 2.1 * rate + seed), sway = Math.sin(t * 0.9 * rate + seed * 2);
  return { spine: 0.7 * sway * amount, chest: 1.1 * breath * amount, neck: 1.4 * sway * amount - 0.5 * breath * amount, shoulderF: 1.4 * breath * amount, shoulderB: -1.2 * breath * amount, elbowF: 0.8 * sway * amount, elbowB: -0.8 * sway * amount };
}

// Two-bone IK in rig-unit coordinates. Picks the elbow/knee side that respects the joint limit.
function limb(root, target, L1, L2, parentAbs, sign, lim1, lim2) {
  const dx = target[0] - root[0], dy = target[1] - root[1], raw = Math.hypot(dx, dy);
  const d = clamp(raw, 0.001, L1 + L2 - 0.001), phi = raw < 1e-6 ? 0 : Math.atan2(dx, dy);
  const A = Math.acos(clamp((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d), -1, 1));
  const hand = along(root, dn(phi), d);
  let best = null;
  for (const a1 of [phi + A, phi - A]) {
    const mid = along(root, dn(a1), L1), a2 = Math.atan2(hand[0] - mid[0], hand[1] - mid[1]);
    const flex = sign * wrap((a2 - a1) / DEG), swing = wrapTo((a1 - parentAbs) / DEG, lim1[0]);
    const score = (swing <= lim1[1] && flex >= lim2[0] ? 1000 : 0) + flex;
    if (!best || score > best.score) best = { swing, flex, score };
  }
  const swing = best.swing <= lim1[1] ? best.swing : (best.swing - lim1[1] < lim1[0] + 360 - best.swing ? lim1[1] : lim1[0]);
  return { swing, flex: clamp(best.flex, lim2[0], lim2[1]) };
}
// Accepts 'F'/'B', and also a joint name such as 'hF' or 'fB' (models often pass those).
const side = (s) => {
  const v = typeof s === 'string' && /^[ehkf]?[FB]$/.test(s) ? s.slice(-1) : null;
  if (!v) throw new TypeError(`Rig side must be 'F' (near limb) or 'B' (far limb), got ${JSON.stringify(s)}. Call rigReach(pose,'F',[x,y]) or rigPlant(pose,'B',[x,y])`);
  return v;
};
const point = (t) => { if (!Array.isArray(t) || t.length !== 2 || !t.every(Number.isFinite)) throw new TypeError('Rig target must be a finite [x,y] array'); return t; };

/** Move a hand to a local-space target [x,y]; the arm stays at its exact length (clamped to reach). */
export function rigReach(pose, s, target, opts = {}) {
  s = side(s); point(target);
  const n = normalise(pose), L = lengths(opts.build), j = points(n, L, [n.x, -((n.height ?? groundHeight(n, L)) + n.lift)]);
  const chestAbs = (n.spine + n.chest) * DEG, r = limb(j.sh, target, L.upperArm, L.foreArm, chestAbs, 1, CHANNELS['shoulder' + s].slice(1), CHANNELS['elbow' + s].slice(1));
  return normalise({ ...n, ['shoulder' + s]: r.swing, ['elbow' + s]: r.flex });
}
/** Plant a foot on a local-space target [x,y] (y=0 is the floor). Freezes hip height so the body does not jump. */
export function rigPlant(pose, s, target, opts = {}) {
  s = side(s); point(target);
  const n = normalise(pose), L = lengths(opts.build), h = n.height ?? groundHeight(n, L), hip = [n.x, -(h + n.lift)];
  const r = limb(hip, target, L.thigh, L.shin, 0, -1, CHANNELS['thigh' + s].slice(1), CHANNELS['knee' + s].slice(1));
  return normalise({ ...n, height: h, ['thigh' + s]: r.swing, ['knee' + s]: r.flex });
}

const WALK = { stride: 40, lift: 12, bob: 2.5, arm: 26, lean: 3, height: 96, duty: 0.58, elbow: 16 };
const RUN = { stride: 70, lift: 32, bob: 7, arm: 42, lean: 12, height: 92, duty: 0.38, elbow: 85 };
const gait = (o) => ({ ...((o.run ? RUN : WALK)), ...o });
const smooth = (k) => k * k * (3 - 2 * k);
function foot(u, g) {
  if (u < g.duty) return [g.stride / 2 - g.stride * (u / g.duty), 0];
  const k = (u - g.duty) / (1 - g.duty);
  return [-g.stride / 2 + g.stride * smooth(k), -g.lift * Math.sin(Math.PI * k)];
}
/**
 * Walk/run cycle with planted feet. phase advances 2*PI per full cycle (two steps).
 * Stance feet stay on the floor and move backward at rigWalkSpeed() so the figure does not skate.
 */
export function rigWalk(phase, o = {}) {
  if (!Number.isFinite(phase)) throw new TypeError('Walk phase must be finite');
  const g = gait(o), u = (((phase / (2 * Math.PI)) % 1) + 1) % 1, ub = (u + 0.5) % 1, c = Math.cos(2 * Math.PI * u);
  const chest = 1.2 * Math.sin(4 * Math.PI * u);
  let p = rigPose('stand', {
    spine: g.lean, chest, neck: 4 - g.lean - chest, height: g.height - g.bob * Math.cos(4 * Math.PI * u), x: o.x ?? 0,
    shoulderF: 6 - g.arm * c, shoulderB: 6 + g.arm * c,
    elbowF: g.elbow + g.arm * 0.45 * (0.5 - 0.5 * c), elbowB: g.elbow + g.arm * 0.45 * (0.5 + 0.5 * c),
  });
  const [fx, fy] = foot(u, g), [bx, by] = foot(ub, g), x = p.x;
  p = rigPlant(p, 'F', [x + fx, fy], o); return rigPlant(p, 'B', [x + bx, by], o);
}
export const rigRun = (phase, o = {}) => rigWalk(phase, { ...o, run: true });
/** Floor speed in rig units/second for a cycle lasting `cycleSeconds`; multiply by the figure scale. */
export function rigWalkSpeed(o = {}, cycleSeconds = 1) {
  const g = gait(o); return g.stride / (g.duty * cycleSeconds);
}

/** Fit a skeleton pose to legacy joint coordinates (bone directions are kept, lengths are corrected). */
export function rigFromJoints(j) {
  for (const k of ['head', 'sh', 'hip', 'eF', 'hF', 'eB', 'hB', 'kF', 'fF', 'kB', 'fB']) if (!Array.isArray(j?.[k]) || j[k].length !== 2 || !j[k].every(Number.isFinite)) throw new TypeError(`Joint ${k} must be a finite [x,y] array`);
  const ang = (a, b) => Math.atan2(b[0] - a[0], b[1] - a[1]) / DEG, tor = Math.atan2(j.sh[0] - j.hip[0], -(j.sh[1] - j.hip[1])) / DEG;
  const o = { spine: tor, chest: 0, neck: wrap(Math.atan2(j.head[0] - j.sh[0], -(j.head[1] - j.sh[1])) / DEG - tor), x: j.hip[0] };
  for (const s of ['F', 'B']) {
    const u = ang(j.sh, j['e' + s]), f = ang(j['e' + s], j['h' + s]), t = ang(j.hip, j['k' + s]), c = ang(j['k' + s], j['f' + s]);
    o['shoulder' + s] = wrapTo(u - tor, CHANNELS['shoulder' + s][1]); o['elbow' + s] = wrap(f - u);
    o['thigh' + s] = wrapTo(t, CHANNELS['thigh' + s][1]); o['knee' + s] = wrap(t - c);
  }
  const n = normalise(o), L = lengths(), floor = Math.max(j.fF[1], j.fB[1]);
  n.lift = Math.max(0, -floor); n.height = Math.max(0, -(j.hip[1]) - n.lift);
  if (Math.abs(n.height - groundHeight(n, L)) < 0.75) delete n.height;
  return normalise(n);
}
