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

    def test_undefined_info_t_is_replaced_by_the_time_argument(self):
        code = "registerShot('s001',{draw(g, t, info){ rigAdd(p, rigIdle(info.t)); const q = info.p + info.dur + info.time; }});"
        scene, fixed = scene_result(json.dumps({'scene': 'Writes in a notebook', 'code': code}), 's001')
        self.assertIn('rigIdle(t)', fixed)
        self.assertIn('info.p + info.dur + info.time', fixed)
        self.assertNotIn('info.t)', fixed)

    def test_missing_rig_imports_are_added_but_local_declarations_are_kept(self):
        code = ("import {E, registerShot} from '/engine/core.js';\n"
                "import {drawFigure, rigPose, rigAdd} from '/engine/rig2d.js';\n"
                "function rigReach(a){return a;}\n"
                "registerShot('s001',{draw(g,t,info){drawFigure(g,{pose:rigAdd(rigPose('stand'),rigIdle(t))});"
                "const h=jointWorld({},'hF');rigReach(h);}});")
        scene, fixed = scene_result(json.dumps({'scene': 'Stands up', 'code': code}), 's001')
        self.assertIn("import {drawFigure, rigPose, rigAdd, rigIdle, jointWorld} from '/engine/rig2d.js'", fixed)
        self.assertEqual(fixed.count('rigReach'), 2)        # local function not imported
        self.assertEqual(scene_result(json.dumps({'scene': 'Stands up', 'code': fixed}), 's001')[1], fixed)

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
                # Approved geometry must not silently survive a new aspect ratio.
                state_path=project/'build/local_animation.json'
                state=json.loads(state_path.read_text())
                state['complete']['s001']['manual']=True
                state_path.write_text(json.dumps(state))
                config_before=(project/'config.json').read_bytes()
                for changed in ({'aspect':'16:9'}, {'style':'ember'}, {'look':'Different costume'}):
                    with self.subTest(changed=changed), self.assertRaisesRegex(RuntimeError,'Approved scenes need review'):
                        animation.execute(**dict(args,**changed))
                self.assertEqual((project/'config.json').read_bytes(),config_before)
                self.assertEqual(request.call_count,2)

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

    def test_setup_failure_saves_timing_and_original_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); voice=root/'voice.mp3';script=root/'script.txt'
            voice.write_bytes(b'x');script.write_text('Start work.')
            animation=LocalAnimation(root,'video','python',lambda cmd:(1,'setup failed'),{},'',lambda:None,lambda _:None)
            with self.assertRaisesRegex(RuntimeError,'setup failed'):
                animation.execute(voice=voice,script=script,title='Video',aspect='9:16',
                                  resolution='720p',style='emerald',captions=True)
            report=json.loads((root/'projects/video/build/ollama_performance.json').read_text())
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['stage'],'project_setup')
            self.assertIn('setup failed',report['error'])

    def test_storyboard_failure_keeps_checkpoint_and_records_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            import hashlib
            root=Path(folder);p=root/'projects/video'
            for rel in ('build','story','timeline'):(p/rel).mkdir(parents=True,exist_ok=True)
            voice=root/'voice.mp3';script=root/'script.txt';voice.write_bytes(b'x');script.write_text('x')
            state={'input':hashlib.sha256(b'xx').hexdigest(),'complete':{},'direction_key':'old',
                   'directions':{'s001':{'action':'Existing storyboard'}}}
            checkpoint=p/'build/local_animation.json';checkpoint.write_text(json.dumps(state))
            (p/'config.json').write_text('{}');(p/'timeline/words.json').write_text('{}')
            (p/'story/shots.json').write_text(json.dumps({'duration':4,'shots':[
                {'id':'s001','start':0,'end':4,'line':'x','scene':'TODO'}]}))
            animation=LocalAnimation(root,'video','python',lambda cmd:(0,''),{},'',lambda:None,lambda _:None)
            with patch.object(animation,'plan_story',side_effect=RuntimeError('planning failed')):
                with self.assertRaisesRegex(RuntimeError,'planning failed'):
                    animation.execute(voice=voice,script=script,title='Video',aspect='9:16',
                                      resolution='720p',style='emerald',captions=True)
            self.assertEqual(json.loads(checkpoint.read_text()),state)
            report=json.loads((p/'build/ollama_performance.json').read_text())
            self.assertEqual((report['status'],report['stage']),('failed','storyboard'))

    def test_alignment_failure_is_included_in_performance_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); p=root/'projects/video'
            voice=root/'voice.mp3';script=root/'script.txt';voice.write_bytes(b'x');script.write_text('x')
            def run(cmd):
                if 'tools/new_project.py' in cmd:
                    (p/'config.json').write_text('{}')
                    return 0,''
                return 1,'alignment failed'
            animation=LocalAnimation(root,'video','python',run,{},'',lambda:None,lambda _:None)
            with self.assertRaisesRegex(RuntimeError,'alignment failed'):
                animation.execute(voice=voice,script=script,title='Video',aspect='9:16',
                                  resolution='720p',style='emerald',captions=True)
            report=json.loads((p/'build/ollama_performance.json').read_text())
            self.assertEqual((report['status'],report['stage']),('failed','alignment'))

    def test_early_cancellation_is_recorded_without_reading_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def cancel():
                raise RuntimeError('Stopped.')
            animation=LocalAnimation(root,'video','python',lambda cmd:(0,''),{},'',cancel,lambda _:None)
            with self.assertRaisesRegex(RuntimeError,'Stopped.'):
                animation.execute(voice='absent',script='absent',title='Video',aspect='9:16',
                                  resolution='720p',style='emerald',captions=True)
            report=json.loads((root/'projects/video/build/ollama_performance.json').read_text())
            self.assertEqual(report['status'],'cancelled')


if __name__ == '__main__':
    unittest.main()
