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
            checkpoint = json.loads((host.project / 'build/host_animation.json').read_text())
            self.assertEqual(checkpoint['completed'], 0)
            self.assertEqual(checkpoint['pending'], 0)
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

    def test_render_failure_preserves_pending_qc_without_export(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, _ = self.fixture(Path(folder), fail_render=True)
            with self.assertRaisesRegex(RuntimeError, 'rendering failed'):
                host.execute(['build'], 10)
            self.assertEqual(json.loads((host.project / 'build/host_animation.json').read_text())['completed'], 0)
            self.assertFalse(any('audio/mix.py' in cmd for cmd in commands))

    def test_third_repair_gets_a_final_render_and_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, prompts = self.fixture(Path(folder), replies=[
                'SCENES_READY', 'QC_FIXED', 'QC_FIXED', 'QC_FIXED', 'QC_OK'])
            host.execute(['build'], 10)
            self.assertEqual(sum('--sheet' in cmd for cmd in commands), 4)
            self.assertIn('FINAL VERIFICATION', prompts[-1])

    def test_pending_qc_resumes_without_another_build_request(self):
        with tempfile.TemporaryDirectory() as folder:
            replies = ['SCENES_READY', 'QC_FIXED', 'QC_FIXED', 'QC_FIXED', 'QC_PENDING']
            host, _, prompts = self.fixture(Path(folder), replies=replies)
            with self.assertRaisesRegex(RuntimeError, 'saved at visual QC'):
                host.execute(['build'], 10)
            prompts.clear()
            replies.append('QC_OK')
            host.execute(['build'], 10)
            self.assertEqual(len(prompts), 1)
            self.assertIn('Visual QC', prompts[0])

    def test_approval_after_editing_requires_another_render(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, _ = self.fixture(Path(folder))
            original = host.ask
            reviews = 0
            def ask(prompt):
                nonlocal reviews
                if 'Visual QC' in prompt:
                    reviews += 1
                    if reviews == 1:
                        (host.project / 'story/shots.json').write_text(
                            (host.project / 'story/shots.json').read_text() + '\n')
                return original(prompt)
            host.ask = ask
            host.execute(['build'], 10)
            self.assertEqual(sum('--sheet' in cmd for cmd in commands), 2)

    def test_rejects_project_paths_outside_studio_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('..', '../escape', 'a/b', 'a\\b'):
                with self.assertRaises(ValueError):
                    HostAnimation(folder, name, 'python', None, None, None)

    def test_local_export_rejects_unfinished_plan_without_accepting_mp4(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, _ = self.fixture(Path(folder))
            plan = host.project / 'story/shots.json'
            story = json.loads(plan.read_text())
            for shot in story['shots']:
                shot['scene'] = 'TODO'
            plan.write_text(json.dumps(story))
            output = host.project / 'out/substitute.mp4'
            output.parent.mkdir()
            output.write_bytes(b'black video with audio')
            with self.assertRaisesRegex(RuntimeError, 'unfinished scene'):
                host.export_local(10)
            self.assertEqual(commands, [])

    def test_local_export_uses_real_renderer_and_validates_streams(self):
        with tempfile.TemporaryDirectory() as folder:
            host, commands, _ = self.fixture(Path(folder))
            plan = host.project / 'story/shots.json'
            story = json.loads(plan.read_text())
            for shot in story['shots']:
                shot['scene'] = 'Character wakes and stretches'
            plan.write_text(json.dumps(story))
            self.assertTrue(Path(host.export_local(10)).exists())
            self.assertIn('--sheet', commands[0])
            self.assertTrue(any('audio/mix.py' in cmd for cmd in commands))
            self.assertEqual(commands[-1][0], 'ffprobe')


if __name__ == '__main__':
    unittest.main()
