"""Keep word captions readable: the highlighted word overlapped its neighbours.

The kit spaces caption words by 0.3 em, but each word also has an outline stroke (0.16 em)
and the current word pops to 1.08x scale. A long highlighted word therefore ate the space
beside it ("PROCRASTINATIONWHISPERS"). The gap now reserves room for the stroke and the pop.
"""
from pathlib import Path

MARKER = '// 2d-studio: caption spacing'
OLD_WIDTH = "const w0 = strs.map(s => measure(g, s, size)).reduce((a, b) => a + b, 0) + size * 0.3 * (strs.length - 1);"
NEW_WIDTH = ("const gapFor = (em, ws) => em * 0.4 + Math.max(0, ...ws) * 0.04;   " + MARKER + "\n"
             "  const w0m = strs.map(s => measure(g, s, size)), w0 = w0m.reduce((a, b) => a + b, 0) + gapFor(size, w0m) * (strs.length - 1);")
OLD_GAP = "const gap = sz * 0.3, widths = strs.map(s => measure(g, s, sz)), total ="
NEW_GAP = "const widths = strs.map(s => measure(g, s, sz)), gap = gapFor(sz, widths), total ="


def patch_captions(studio):
    path = Path(studio) / 'engine/ui2d.js'
    source = path.read_text(encoding='utf-8')
    if MARKER in source:
        return False
    if OLD_WIDTH not in source or OLD_GAP not in source:
        raise RuntimeError('Unknown caption layout; refusing to patch')
    source = source.replace(OLD_WIDTH, NEW_WIDTH, 1).replace(OLD_GAP, NEW_GAP, 1)
    path.write_text(source, encoding='utf-8')
    return True
