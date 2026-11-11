import json
from pathlib import Path
import tempfile
import unittest

from host_render import HostAnimation


class HostRenderTests(unittest.TestCase):
    def fixture(self, root, replies=None, fail_render=False):
        project = root / 'projects' / 'video'
        (project / 'story').mkdir(parents=True)
        (project / 'story/shots.json').write_text(json.dumps({'shots': [
            {'id': 's1', 'start': 0, 'end': 5}, {'id': 's2', 'start': 5, 'end': 10}]}))
        commands, prompts = [], []
        def run(cmd):
            commands.append(cmd)
            if cmd[0] == 'node':
                if fail_render:
                    return 1, 'shot error: broken scene'
                folder = project / 'build' / ('sheets' if '--sheet' in cmd else 'stills')
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'sheet_001.png').write_bytes(b'image')
            elif 'audio/mix.py' in cmd:
                out = Path(cmd[-1]); out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(b'video')
            elif cmd[0] == 'ffprobe':
                return 0, json.dumps({'streams': [{'codec_type': 'audio'}, {'codec_type': 'video'}],
                                     'format': {'duration': '10'}})
            return 0, 'ok'
        def ask(prompt):
            prompts.append(prompt)
            if replies is not None:
                return replies.pop(0)
            return 'QC_OK' if 'Visual QC' in prompt else 'SCENES_READY'
        return HostAnimation(root, 'video', 'python', run, ask, lambda: None), commands, prompts

    def test_app_renders_mixes_and_resumes_only_visually_approved_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, prompts = self.fixture(Path(folder))
            result = host.execute(['build first half', 'final pass'], 10)
            self.assertTrue(Path(result).exists())
            self.assertTrue(any('--stills' in cmd for cmd in commands))
            self.assertTrue(any('--sheet' in cmd for cmd in commands))
            self.assertTrue(any('audio/mix.py' in cmd for cmd in commands))
            self.assertIn('APP-MANAGED RENDERING', prompts[0])
            prompts.clear()
            host.execute(['build first half', 'final pass'], 10)
            self.assertEqual(prompts, [])

    def test_uninspected_images_never_advance_checkpoint_or_export(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, _ = self.fixture(Path(folder), replies=['SCENES_READY', 'Cannot inspect images.'])
            with self.assertRaisesRegex(RuntimeError, 'not approved'):
                host.execute(['build'], 10)
            self.assertFalse((host.project / 'build/host_animation.json').exists())
            self.assertFalse(any('audio/mix.py' in cmd for cmd in commands))

    def test_scene_changes_invalidate_completed_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            host, _, prompts = self.fixture(Path(folder))
            host.execute(['build'], 10)
            scene = host.project / 'scenes' / 'shot.js'
            scene.parent.mkdir()
            scene.write_text('// changed after QC')
            prompts.clear()
            host.execute(['build'], 10)
            self.assertTrue(any('Visual QC' in prompt for prompt in prompts))

    def test_visual_fixes_require_a_new_render_before_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, _ = self.fixture(Path(folder), replies=['SCENES_READY', 'QC_FIXED', 'QC_OK'])
            host.execute(['build'], 10)
            self.assertEqual(sum('--sheet' in cmd for cmd in commands), 2)

    def test_render_failure_stops_without_checkpoint_or_export(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, _ = self.fixture(Path(folder), fail_render=True)
            with self.assertRaisesRegex(RuntimeError, 'rendering failed'):
                host.execute(['build'], 10)
            self.assertFalse((host.project / 'build/host_animation.json').exists())
            self.assertFalse(any('audio/mix.py' in cmd for cmd in commands))

    def test_rejects_project_paths_outside_studio_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('..', '../escape', 'a/b', 'a\\b'):
                with self.assertRaises(ValueError):
                    HostAnimation(folder, name, 'python', None, None, None)


if __name__ == '__main__':
    unittest.main()
