// Probe real encodes: an encoder listed by FFmpeg may lack a usable driver/device.
import { spawnSync } from 'node:child_process';

export function selectEncoder(pref, width, height, crf = 18, preset = 'medium', run = spawnSync) {
  pref = String(pref).toLowerCase();
  if (!['auto', 'cpu', 'gpu', 'nvenc', 'qsv', 'amf'].includes(pref))
    throw new Error('encoder must be auto, cpu, gpu, nvenc, qsv or amf');
  const cpu = { name: 'libx264', gpu: false, options: ['-c:v', 'libx264', '-preset', preset, '-crf', String(crf)] };
  if (pref === 'cpu') return cpu;
  const candidates = [
    ['nvenc', 'h264_nvenc', ['-preset', 'p5', '-tune', 'hq', '-rc', 'vbr', '-cq', String(+crf + 1), '-b:v', '0']],
    ['qsv', 'h264_qsv', ['-preset', 'medium', '-global_quality', String(+crf + 1)]],
    ['amf', 'h264_amf', ['-quality', 'balanced', '-rc', 'cqp', '-qp_i', String(crf), '-qp_p', String(+crf + 2)]],
  ];
  for (const [id, name, quality] of candidates) {
    if (!['auto', 'gpu', id].includes(pref)) continue;
    const options = ['-c:v', name, ...quality];
    const probe = run('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i',
      `color=c=black:s=${width}x${height}:r=24`, '-frames:v', '2', ...options,
      '-pix_fmt', 'yuv420p', '-f', 'null', '-'], { timeout: 15000, windowsHide: true, encoding: 'utf8' });
    if (probe.status === 0) return { name, gpu: true, options };
    console.log(`[encoder] ${name} unavailable; trying fallback`);
  }
  return cpu;
}
