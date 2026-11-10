import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selectEncoder } from './video_encoder.mjs';

test('CPU override never probes hardware', () => {
  assert.equal(selectEncoder('cpu', 1920, 1080, 18, 'medium', () => { throw Error('unexpected probe'); }).name, 'libx264');
});
test('missing drivers fall through to Intel then CPU', () => {
  const seen = [];
  const run = (_, args) => { const name = args[args.indexOf('-c:v') + 1]; seen.push(name); return { status: name === 'h264_qsv' ? 0 : 1 }; };
  assert.equal(selectEncoder('auto', 1920, 1080, 18, 'medium', run).name, 'h264_qsv');
  assert.deepEqual(seen, ['h264_nvenc', 'h264_qsv']);
  assert.equal(selectEncoder('gpu', 1920, 1080, 18, 'medium', () => ({ status: null })).name, 'libx264');
});
test('explicit AMD probe uses output dimensions and CPU fallback', () => {
  let calls = 0;
  const result = selectEncoder('amf', 720, 1280, 20, 'fast', (_, args) => {
    calls++;
    assert.ok(args.includes('color=c=black:s=720x1280:r=24'));
    assert.ok(args.includes('h264_amf'));
    return { status: 1 };
  });
  assert.equal(calls, 1);
  assert.equal(result.name, 'libx264');
  assert.ok(result.options.includes('fast'));
});
