import tempfile
import unittest
from pathlib import Path

from patch_captions import MARKER, OLD_GAP, OLD_WIDTH, patch_captions

KIT_SOURCE = (
    "export function captions(g, globalT, o = {}) {\n"
    "  const strs = ['A'];\n"
    "  " + OLD_WIDTH + "\n"
    "  const sz = size * Math.min(1, (E.W * 0.88) / w0);\n"
    "  " + OLD_GAP + " widths.reduce((a, b) => a + b, 0) + gap * (strs.length - 1);\n"
    "}\n"
)


class CaptionPatchTests(unittest.TestCase):
    def studio(self, source):
        root = Path(tempfile.mkdtemp())
        (root / 'engine').mkdir()
        (root / 'engine/ui2d.js').write_text(source, encoding='utf-8')
        return root

    def test_gap_reserves_room_for_stroke_and_pop_and_patch_is_idempotent(self):
        root = self.studio(KIT_SOURCE)
        self.assertTrue(patch_captions(root))
        patched = (root / 'engine/ui2d.js').read_text(encoding='utf-8')
        self.assertIn(MARKER, patched)
        self.assertNotIn('sz * 0.3', patched)
        self.assertNotIn('size * 0.3', patched)
        self.assertIn('gap = gapFor(sz, widths)', patched)
        self.assertIn('gapFor(size, w0m)', patched)
        self.assertFalse(patch_captions(root))
        self.assertEqual(patched, (root / 'engine/ui2d.js').read_text(encoding='utf-8'))

    def test_unknown_caption_layout_is_refused_and_left_alone(self):
        root = self.studio('export function captions() {}\n')
        with self.assertRaisesRegex(RuntimeError, 'Unknown caption layout'):
            patch_captions(root)
        self.assertEqual((root / 'engine/ui2d.js').read_text(encoding='utf-8'), 'export function captions() {}\n')


if __name__ == '__main__':
    unittest.main()
