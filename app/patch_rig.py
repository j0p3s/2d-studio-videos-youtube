"""Install portable rig safety fixes and the skeletal rig without altering the approved pose designs."""
from pathlib import Path
import shutil

SKELETON_MARKER = '// 2d-studio: skeletal rig'


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
    if 'restOn' not in source:
        # Lying figures rotate around the hip, so y is not the feet; restOn places the body on a surface.
        export="export {clonePose, armPose, jointWorld};"
        if export not in source:
            raise RuntimeError('Unknown rig export line; refusing to add surface helpers')
        source=source.replace(export,export+"\nexport {restOn, surfaceGap, figureLowest} from './rig_safety.mjs';",1)
        path.write_text(source,encoding='utf-8')
    if SKELETON_MARKER not in source:
        # Skeleton poses (rigPose/rigWalk/...) are angle based and solve to the same 11 joints the
        # renderer draws, so drawFigure/headPos accept either representation.
        draw="  assertPose(o.pose || POSES.stand);"
        head="export function headPos(o) { const p = o.pose || POSES.stand,"
        if draw not in source or head not in source:
            raise RuntimeError('Unknown rig draw API; refusing to add the skeletal rig')
        source=source.replace(draw,"  if (isRigPose(o.pose)) o = { ...o, pose: rigJoints(o.pose, { build: o.build }) };\n"+draw,1)
        source=source.replace(head,"export function headPos(o) { const p = isRigPose(o.pose) ? rigJoints(o.pose, { build: o.build }) : (o.pose || POSES.stand),",1)
        source=SKELETON_MARKER+"\nimport {isRigPose, rigJoints} from './skeleton.mjs';\nexport * from './skeleton.mjs';\n"+source
        path.write_text(source,encoding='utf-8')
    here=Path(__file__).parent
    for name in ('rig_safety.mjs','skeleton.mjs'):
        shutil.copy2(here/name,Path(studio)/'engine'/name)
