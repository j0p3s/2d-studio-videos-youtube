import test from 'node:test';
import assert from 'node:assert/strict';
import { JOINTS } from './rig_safety.mjs';
import {
  RIG, RIG_POSE_NAMES, RIG_CHANNELS, isRigPose, rigPose, rigJoints, rigBlend, rigSample, rigAdd, rigIdle,
  rigReach, rigPlant, rigWalk, rigRun, rigWalkSpeed, rigFromJoints, rigGroundHeight,
} from './skeleton.mjs';

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
function bones(j) {
  return {
    spine: dist(j.hip, j.sh), neck: dist(j.sh, j.head),
    upF: dist(j.sh, j.eF), foreF: dist(j.eF, j.hF), upB: dist(j.sh, j.eB), foreB: dist(j.eB, j.hB),
    thF: dist(j.hip, j.kF), shF: dist(j.kF, j.fF), thB: dist(j.hip, j.kB), shB: dist(j.kB, j.fB),
  };
}
function assertLengths(j, msg = '') {
  const b = bones(j), eq = (a, e, k) => assert.ok(Math.abs(a - e) < 1e-6, `${msg} ${k} ${a} != ${e}`);
  // hip->shoulder is two bones, so a bent chest legitimately shortens the straight-line distance.
  assert.ok(b.spine <= RIG.spine + RIG.chest + 1e-6 && b.spine >= 40, `${msg} spine ${b.spine}`); eq(b.neck, RIG.neck, 'neck');
  eq(b.upF, RIG.upperArm, 'upF'); eq(b.foreF, RIG.foreArm, 'foreF'); eq(b.upB, RIG.upperArm, 'upB'); eq(b.foreB, RIG.foreArm, 'foreB');
  eq(b.thF, RIG.thigh, 'thF'); eq(b.shF, RIG.shin, 'shF'); eq(b.thB, RIG.thigh, 'thB'); eq(b.shB, RIG.shin, 'shB');
}
const finite = (j) => JOINTS.every((k) => j[k].every(Number.isFinite));

test('every named pose solves to the renderer joints with exact bone lengths and feet on the floor', () => {
  for (const name of RIG_POSE_NAMES) {
    const p = rigPose(name), j = rigJoints(p);
    assert.deepEqual(Object.keys(j).sort(), [...JOINTS].sort());
    assert.ok(finite(j), name); assertLengths(j, name);
    assert.ok(isRigPose(p));
    assert.ok(Math.abs(Math.max(j.fF[1], j.fB[1])) < 1e-9, `${name} floor`);
  }
});
test('standing pose matches the legacy proportions (head ~208 above feet)', () => {
  const j = rigJoints(rigPose('stand'));
  assert.ok(Math.abs(-j.head[1] - 208) < 4, String(j.head));
  assert.ok(Math.abs(-j.hip[1] - 100) < 1.5);
});
test('random and extreme angles never stretch bones and are clamped to anatomical limits', () => {
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 300; i++) {
    const o = {}; for (const k of RIG_CHANNELS) o[k] = (rnd() - 0.5) * 1200;
    const p = rigPose('stand', o), j = rigJoints(p);
    assert.ok(finite(j)); assertLengths(j, 'random');
    assert.ok(p.kneeF >= 0 && p.kneeB >= 0 && p.elbowF >= -8 && p.elbowF <= 155);
  }
});
test('typos and non-finite channels fail loudly instead of drawing garbage', () => {
  assert.throws(() => rigPose('stand', { shoulderL: 10 }), /Unknown rig channel/);
  assert.throws(() => rigPose('stand', { elbowF: NaN }), /finite/);
  assert.throws(() => rigPose('wobble'), /Unknown rig pose/);
  assert.throws(() => rigReach(rigPose(), 'X', [0, 0]), /side/);
  assert.throws(() => rigReach(rigPose(), 'F', [NaN, 0]), /finite/);
  assert.throws(() => rigJoints(rigPose(), { build: 'giant' }), /Unknown rig build/);
});
test('rigPose never aliases or mutates its inputs', () => {
  const base = rigPose('talk'), copy = rigPose(base, { neck: 30 });
  assert.equal(base.neck, 5); assert.equal(copy.neck, 30); assert.notEqual(base, copy);
});
test('blending keeps limb length at every step, unlike coordinate lerp', () => {
  for (const k of [0, 0.25, 0.5, 0.75, 1]) assertLengths(rigJoints(rigBlend('stand', 'cheer', k)), 'blend');
  const a = rigJoints(rigPose('stand')), b = rigJoints(rigPose('cheer'));
  const mid = { hF: [(a.hF[0] + b.hF[0]) / 2, (a.hF[1] + b.hF[1]) / 2] };
  assert.ok(dist(a.sh, mid.hF) < RIG.upperArm + RIG.foreArm - 5, 'coordinate lerp shortens the arm (the old defect)');
  assert.equal(rigBlend('stand', 'cheer', 0).shoulderF, rigPose('stand').shoulderF);
  assert.equal(rigBlend('stand', 'cheer', 1).shoulderF, rigPose('cheer').shoulderF);
});
test('keyframe sampler eases between keys, holds outside them and supports hold mode', () => {
  const keys = [[0, 'stand'], [1, 'cheer'], [2, 'point']];
  assert.equal(rigSample(keys, -5).shoulderF, rigPose('stand').shoulderF);
  assert.equal(rigSample(keys, 9).shoulderF, rigPose('point').shoulderF);
  const mid = rigSample(keys, 0.5).shoulderF; assert.ok(mid > rigPose('stand').shoulderF && mid < rigPose('cheer').shoulderF);
  assert.equal(rigSample(keys, 0.9, { mode: 'hold' }).shoulderF, rigPose('stand').shoulderF);
  assert.equal(rigSample([[2, 'point'], [0, 'stand'], [1, 'cheer']], 1).shoulderF, rigPose('cheer').shoulderF);
  assert.throws(() => rigSample([], 0), /needs keys/);
});
test('rigReach places the hand exactly on reachable targets and clamps unreachable ones', () => {
  const base = rigPose('stand'), sh = rigJoints(base).sh;
  for (const target of [[sh[0] + 40, sh[1] + 20], [sh[0] + 30, sh[1] - 30], [sh[0] + 10, sh[1] + 60], [sh[0] - 10, sh[1] + 55]]) {
    for (const s of ['F', 'B']) {
      const j = rigJoints(rigReach(base, s, target)); assertLengths(j, 'reach');
      assert.ok(dist(j['h' + s], target) < 1e-4, `${s} ${dist(j['h' + s], target)}`);
    }
  }
  const far = rigJoints(rigReach(base, 'F', [5000, -3000])); assertLengths(far, 'far'); assert.ok(finite(far));
  assert.ok(dist(far.sh, far.hF) <= RIG.upperArm + RIG.foreArm + 1e-6);
  const behind = rigReach(base, 'F', [sh[0] - 30, sh[1] + 25]); // beyond shoulder extension: clamps to the limit, stays valid
  assertLengths(rigJoints(behind)); assert.ok(behind.shoulderF <= 200 && behind.shoulderF >= -80 && behind.shoulderF < 0);
  const onShoulder =rigJoints(rigReach(base, 'F', sh)); assert.ok(finite(onShoulder)); assertLengths(onShoulder);
  assert.equal(base.shoulderF, 12, 'input pose untouched');
});
test('elbows bend the natural way when reaching (forearm folds forward, never backwards)', () => {
  const p = rigReach(rigPose('stand'), 'F', [30, -150]);
  assert.ok(p.elbowF >= 0 && p.elbowF <= 155);
});
test('rigPlant puts the foot on the target without moving the hip', () => {
  const base = rigPose('stand'), hip = rigJoints(base).hip;
  const p = rigPlant(base, 'F', [hip[0] + 20, -20]), j = rigJoints(p);
  assertLengths(j); assert.deepEqual(j.hip, hip);
  assert.ok(dist(j.fF, [hip[0] + 20, -20]) < 1e-4);
  assert.ok(j.kF[0] > j.hip[0], 'knee points forward');
});
test('walk cycle: stance foot stays planted and slides back at constant speed, swing foot lifts', () => {
  const o = {}, dphi = 0.01; let prevX = null;
  const speed = rigWalkSpeed(o, 2 * Math.PI); // cycle of 2*PI seconds so phase == seconds
  for (let phase = 0.05; phase < 2 * Math.PI * 0.55; phase += dphi) {
    const j = rigJoints(rigWalk(phase)); assertLengths(j, 'walk');
    assert.ok(Math.abs(j.fF[1]) < 1e-3, `stance foot lifted at ${phase}: ${j.fF[1]}`);
    if (prevX !== null) assert.ok(Math.abs((prevX - j.fF[0]) / dphi - speed) < 0.5, `foot slides at ${phase}`);
    prevX = j.fF[0];
  }
  let maxLift = 0; for (let ph = 0; ph < 2 * Math.PI; ph += 0.05) { const j = rigJoints(rigWalk(ph)); maxLift = Math.max(maxLift, -j.fF[1], -j.fB[1]); assert.ok(finite(j)); }
  assert.ok(maxLift > 10 && maxLift < 16, String(maxLift));
});
test('walk keeps the legs alternating and the head level; negative and huge phases are fine', () => {
  const a = rigJoints(rigWalk(0)), b = rigJoints(rigWalk(Math.PI));
  assert.ok(a.fF[0] > a.fB[0] && b.fF[0] < b.fB[0]);
  assert.ok(Math.abs(rigJoints(rigWalk(1)).head[1] - rigJoints(rigWalk(1 + 2 * Math.PI)).head[1]) < 1e-9);
  for (const ph of [-3, -1e4, 1e6]) assert.ok(finite(rigJoints(rigWalk(ph))));
  assert.throws(() => rigWalk(NaN), /finite/);
});
test('run has a flight phase with both feet off the floor, leans forward and keeps bone lengths', () => {
  let flight = false, minHead = Infinity;
  for (let ph = 0; ph < 2 * Math.PI; ph += 0.02) {
    const j = rigJoints(rigRun(ph)); assertLengths(j, 'run'); assert.ok(finite(j));
    if (j.fF[1] < -2 && j.fB[1] < -2) flight = true; minHead = Math.min(minHead, j.head[1]);
  }
  assert.ok(flight, 'no flight phase'); assert.ok(rigPose('stand').neck !== undefined);
  assert.ok(rigRun(0).spine > rigWalk(0).spine);
  assert.ok(rigWalkSpeed({ run: true }, 0.5) > rigWalkSpeed({}, 0.5));
});
test('idle layer is additive, small and stays within limits', () => {
  const base = rigPose('talk'), p = rigAdd(base, rigIdle(1.3, { amount: 1 }));
  assert.ok(Math.abs(p.chest - base.chest) < 3 && p.shoulderF !== base.shoulderF);
  assertLengths(rigJoints(rigAdd(rigPose('crossArms'), rigIdle(2, { amount: 50 }))));
});
test('legacy joint poses convert to skeleton poses with corrected bone lengths', () => {
  const legacy = { head: [3, -208], sh: [0, -174], hip: [0, -100], eF: [9, -137], hF: [13, -101], eB: [-7, -136], hB: [-9, -100], kF: [6, -50], fF: [3, 0], kB: [-6, -50], fB: [-11, 0] };
  const j = rigJoints(rigFromJoints(legacy)); assertLengths(j);
  for (const k of ['head', 'sh', 'hip', 'hF', 'hB', 'fF', 'fB']) assert.ok(dist(j[k], legacy[k]) < 7, `${k} ${j[k]} vs ${legacy[k]}`);
  const stretched = { ...legacy, hF: [90, -170] };
  assert.ok(dist(stretched.sh, stretched.hF) > 76 || true); assertLengths(rigJoints(rigFromJoints(stretched)));
  assert.throws(() => rigFromJoints({ head: [0, 0] }), /Joint/);
});
test('body builds scale bones consistently and ground the feet', () => {
  const tall = rigJoints(rigPose('stand'), { build: 'tall' }), std = rigJoints(rigPose('stand'));
  assert.ok(-tall.head[1] > -std.head[1]); assert.ok(Math.abs(tall.fF[1]) < 1e-9);
  assert.ok(rigGroundHeight(rigPose('stand'), { build: 'tall' }) > rigGroundHeight(rigPose('stand')));
  assert.ok(Math.abs(dist(tall.sh, tall.eF) - RIG.upperArm * 1.05) < 1e-6);
});
test('lift raises the whole figure (jumps) and x moves it sideways', () => {
  const a = rigJoints(rigPose('stand')), b = rigJoints(rigPose('stand', { lift: 40, x: 15 }));
  assert.ok(Math.abs(b.hip[1] - (a.hip[1] - 40)) < 1e-9 && Math.abs(b.hip[0] - 15) < 1e-9);
});
test('geometry audit accepts every solved skeleton pose and gait frame', async () => {
  const { inspectFigure } = await import('./offline_geometry.mjs');
  const legacy = { head: [3, -208], sh: [0, -174], hip: [0, -100], eF: [9, -137], hF: [13, -101], eB: [-7, -136], hB: [-9, -100], kF: [6, -50], fF: [3, 0], kB: [-6, -50], fB: [-11, 0] };
  const baseline = { stand: legacy, ...Object.fromEntries(RIG_POSE_NAMES.map((n) => [n, rigJoints(rigPose(n))])) };
  const check = (p, build) => inspectFigure({ x: 100, y: 100, s: 1, pose: rigJoints(p, { build }) }, baseline);
  for (const n of RIG_POSE_NAMES) assert.deepEqual(check(rigPose(n)), [], n);
  for (let ph = 0; ph < 2 * Math.PI; ph += 0.1) { assert.deepEqual(check(rigWalk(ph)), [], 'walk'); assert.deepEqual(check(rigRun(ph)), [], 'run'); }
  assert.deepEqual(check(rigPose('explain'), 'tall'), []);
});
test('rig poses expose read-only solved joints so legacy code like pose.hF[0] keeps working', () => {
  const p = rigAdd(rigReach(rigPose('sit'), 'F', [40, -90]), rigIdle(1));
  const j = rigJoints(p);
  for (const k of JOINTS) assert.deepEqual(p[k], j[k], k);
  assert.ok(Number.isFinite(p.hF[0]) && Number.isFinite(p.hF[1]));
  assert.ok(!Object.keys(p).some((k) => JOINTS.includes(k)), 'joints must not be enumerable');
  const copy = { ...p, shoulderF: 90 };                         // copies keep only channels
  assert.equal(copy.hF, undefined); assert.ok(Number.isFinite(rigJoints(copy).hF[0]));
  const live = rigPose('stand'); const before = live.hF[1]; live.shoulderF = 150;
  assert.ok(live.hF[1] < before, 'joint getters follow later channel edits');
  assert.equal(rigPose(p).shoulderF, p.shoulderF);
});
test('passing joint names to rigPose explains the difference between angles and positions', () => {
  assert.throws(() => rigPose('stand', { head: [0, -200] }), /joint POSITION.*rigReach.*jointWorld/);
  assert.throws(() => rigPose('stand', { hF: [1, 2] }), /joint POSITION/);
  assert.throws(() => rigPose('stand', { neckF: 3 }), /Unknown rig channel 'neckF'/);
});
