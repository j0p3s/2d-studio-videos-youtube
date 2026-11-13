import json
from pathlib import Path
import tempfile
import unittest
import shutil
import subprocess
from unittest.mock import patch

from local_animation import LocalAnimation, scene_result, normalize_source, validate_storyboard


class LocalAnimationTests(unittest.TestCase):
    def test_escaped_layout_is_decoded_without_changing_js_literals(self):
        source = r'''import {E} from '/engine/core.js';\n// character's hand\nconst p = /\n/;\nconst label = 'ação\n次';\nconst template = `keep\nthis`;\nregisterShot('s001', {});'''
        expected = "import {E} from '/engine/core.js';\n// character's hand\nconst p = /\\n/;\nconst label = 'ação\\n次';\nconst template = `keep\\nthis`;\nregisterShot('s001', {});"
        self.assertEqual(normalize_source(source), expected)
        self.assertEqual(normalize_source(expected), expected)

    def test_regular_source_and_division_are_preserved(self):
        source = "const a = 20 / 2;\nconst b = 'literal\\n';\nconst c = /[\\/\\n]/;"
        self.assertEqual(normalize_source(source), source)

    @unittest.skipUnless(shutil.which('node'), 'Node required for real syntax verification')
    def test_double_encoded_source_passes_real_node_after_normalization(self):
        source = r'''import {E} from '/engine/core.js';\n// character's hand\nconst label = 'ação\n次';\nconst pattern = /[\n/]/;\nregisterShot('s001', {draw(g,t,info){}});'''
        def check(code):
            return subprocess.run(['node', '--check', '--input-type=module'], input=code,
                                  encoding='utf-8', capture_output=True).returncode
        self.assertNotEqual(check(source), 0)
        self.assertEqual(check(normalize_source(source)), 0)

    def test_model_cannot_choose_output_path_or_register_other_shots(self):
        for code in ("registerShot('../escape',{})", "registerShot('s001',{});registerShot('s002',{})"):
            with self.assertRaises(ValueError):
                scene_result(json.dumps({'scene': 'Reaches for water', 'code': code}), 's001')

    def test_resume_reuses_scenes_but_changed_input_regenerates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            voice, script = root / 'voice.mp3', root / 'script.txt'
            voice.write_bytes(b'voice'); script.write_text('Drink water.')
            project = root / 'projects/video'
            calls = []
            def run(cmd):
                calls.append(cmd)
                if 'tools/new_project.py' in cmd:
                    project.mkdir(parents=True, exist_ok=True)
                    (project / 'config.json').write_text(json.dumps({'duration': 4}))
                if 'tools/transcribe.py' in cmd:
                    (project / 'timeline').mkdir(exist_ok=True)
                    (project / 'timeline/words.json').write_text('{}')
                if 'tools/beats.py' in cmd:
                    (project / 'story').mkdir(exist_ok=True)
                    (project / 'story/shots.json').write_text(json.dumps({'duration': 4, 'shots': [
                        {'id': 's001', 'start': 0, 'end': 4, 'line': 'Drink water.', 'scene': 'TODO'}]}))
                return 0, 'ok'
            animation = LocalAnimation(root, 'video', 'python', run, {}, 'gpt-oss-test', lambda: None, lambda _: None)
            args = dict(voice=voice, script=script, title='Video', aspect='9:16', resolution='720p',
                        style='emerald', captions=True)
            response = json.dumps({'scene': 'Reaches for water',
                                   'code': "registerShot('s001',{draw(g,t,info){}})"})
            with patch.object(animation, 'request', return_value=response) as request, \
                    patch.object(animation, 'plan_story', return_value={'s001': {'action': 'Reach for the glass'}}), \
                    patch('check_offline_scenes.check_project'), \
                    patch.object(animation.host, 'export', return_value='final.mp4'), \
                    patch('local_animation.ollama_provider.release_model'):
                animation.execute(**args)
                animation.execute(**args)
                self.assertEqual(request.call_count, 1)
                script.write_text('Stretch first.')
                animation.execute(**args)
                self.assertEqual(request.call_count, 2)
                self.assertTrue((project / 'build/ollama_performance.json').exists())

    def test_malformed_responses_stop_after_three_attempts_without_export(self):
        with tempfile.TemporaryDirectory() as folder:
            # Resume a prepared project, avoiding external tools in this failure check.
            root = Path(folder); project = root / 'projects/video'
            (project / 'build').mkdir(parents=True)
            (project / 'timeline').mkdir(); (project / 'story').mkdir()
            voice, script = root / 'voice.mp3', root / 'script.txt'
            voice.write_bytes(b'x'); script.write_text('x')
            import hashlib
            (project / 'build/local_animation.json').write_text(json.dumps({'input': hashlib.sha256(b'xx').hexdigest()}))
            (project / 'config.json').write_text('{}')
            (project / 'timeline/words.json').write_text('{}')
            (project / 'story/shots.json').write_text(json.dumps({'duration': 4, 'shots': [
                {'id': 's001', 'start': 0, 'end': 4, 'line': 'x', 'scene': 'TODO'}]}))
            animation = LocalAnimation(root, 'video', 'python', lambda _: (0, ''), {}, '', lambda: None, lambda _: None)
            with patch.object(animation, 'request', return_value='bad json') as request, \
                    patch.object(animation, 'plan_story', return_value={'s001': {'action': 'Reach for the glass'}}), \
                    patch.object(animation.host, 'export') as export:
                with self.assertRaisesRegex(RuntimeError, 'after 3 attempts'):
                    animation.execute(voice=voice, script=script, title='x', aspect='9:16',
                                      resolution='720p', style='emerald', captions=True)
                self.assertEqual(request.call_count, 3)
                export.assert_not_called()

    def test_storyboard_rejects_repetitive_framing_and_incomplete_action(self):
        shots = [{'id': f's{i:03d}'} for i in range(4)]
        items = [dict(id=s['id'], framing='medium', setting='A warm window-lit office',
                      action='Complete task number '+str(i), start_state='Hands resting on desk',
                      end_state='Right hand finishes typing') for i, s in enumerate(shots)]
        with self.assertRaisesRegex(ValueError, 'four consecutive'):
            validate_storyboard(json.dumps({'shots': items}), shots)
        items[1]['framing'] = 'insert'
        self.assertEqual(len(validate_storyboard(json.dumps({'shots': items}), shots)), 4)
        items[2]['end_state'] = items[2]['start_state']
        with self.assertRaisesRegex(ValueError, 'different start and end'):
            validate_storyboard(json.dumps({'shots': items}), shots)


if __name__ == '__main__':
    unittest.main()
