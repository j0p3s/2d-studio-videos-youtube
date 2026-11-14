import tempfile
import unittest
from pathlib import Path

from patch_rig import patch_rig

RIG = """const POSES = {stand: {}};
export const pose = (name) => POSES[name] || POSES.stand;
export function drawFigure(g, o) {
  const d0 = 1;
  d = Math.min(d, L1 + L2 - 0.01);
}
export function headPos(o) { const p = o.pose || POSES.stand, s = 1; return p; }
"""


class PatchRigTest(unittest.TestCase):
    def studio(self, tmp):
        engine = Path(tmp) / 'engine'
        engine.mkdir()
        (engine / 'rig2d.js').write_text(RIG, encoding='utf-8')
        return Path(tmp)

    def test_exports_surface_helpers_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = self.studio(tmp)
            patch_rig(studio)
            patch_rig(studio)
            source = (studio / 'engine/rig2d.js').read_text(encoding='utf-8')
            self.assertEqual(source.count("export {restOn, surfaceGap, figureLowest} from './rig_safety.mjs';"), 1)
            self.assertIn('restOn', (studio / 'engine/rig_safety.mjs').read_text(encoding='utf-8'))

    def test_upgrades_a_studio_patched_before_the_helpers_existed(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = self.studio(tmp)
            patch_rig(studio)
            path = studio / 'engine/rig2d.js'
            path.write_text(path.read_text(encoding='utf-8').replace(
                "export {restOn, surfaceGap, figureLowest} from './rig_safety.mjs';\n", ''), encoding='utf-8')
            patch_rig(studio)
            self.assertIn('restOn', path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
