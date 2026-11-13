"""Install portable rig safety fixes without altering the approved pose designs."""
from pathlib import Path
import shutil

def patch_rig(studio):
    path=Path(studio)/'engine/rig2d.js'
    source=path.read_text(encoding='utf-8')
    if '// 2d-studio: safe pose copies' not in source:
        original="export const pose = (name) => POSES[name] || POSES.stand;"
        if original not in source:
            raise RuntimeError('Unknown rig pose API; refusing to patch')
        source=source.replace(original,"// 2d-studio: safe pose copies\nexport const pose = (name) => clonePose(POSES[name] || POSES.stand);")
        source="import {clonePose, assertPose, armPose, jointWorld} from './rig_safety.mjs';\nexport {clonePose, armPose, jointWorld};\n"+source
        signature='export function drawFigure(g, o) {'
        if signature not in source:
            raise RuntimeError('Unknown rig draw API; refusing to patch')
        source=source.replace(signature,signature+"\n  assertPose(o.pose || POSES.stand);\n  if (![o.x,o.y,o.s??1,o.facing??1,o.rot??0].every(Number.isFinite)) throw new TypeError('Non-finite figure transform');")
        source=source.replace('d = Math.min(d, L1 + L2 - 0.01);','d = Math.max(0.001, Math.min(d, L1 + L2 - 0.01));')
        path.write_text(source,encoding='utf-8')
    shutil.copy2(Path(__file__).with_name('rig_safety.mjs'),Path(studio)/'engine/rig_safety.mjs')
