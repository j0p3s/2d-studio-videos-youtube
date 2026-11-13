import json
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import castworkshop_provider as cast
from ai_providers import PROVIDERS, TEXT_PROVIDERS
import model_choices


class CastWorkshopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = cast.Session(self.root, cast.DEFAULT_URL, self.root / 'cache', env={},
                                    check=lambda: None, log=lambda _: None)
        self.destination = self.root / 'build/shot_001_image'
        self.graph = {'57': {'class_type': 'SaveImage', 'inputs': {}}}

    def test_animation_only_provider(self):
        self.assertIn(cast.CASTWORKSHOP, PROVIDERS)
        self.assertNotIn(cast.CASTWORKSHOP, TEXT_PROVIDERS)
        self.assertIn('workflow models', model_choices.available(cast.CASTWORKSHOP, {})[1])

    def test_remote_or_credentialed_endpoints_are_rejected(self):
        for url in ('https://localhost:8190', 'http://example.com', 'http://127.0.0.1.evil.test',
                    'http://user:pass@localhost:8190', 'http://localhost/other', 'http://localhost/?token=x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                cast.local_url(url)
        self.assertEqual(cast.local_url('http://127.0.0.1:8190/'), cast.DEFAULT_URL)

    def test_missing_installation_has_clear_readiness_errors(self):
        problems = cast.readiness(self.root)
        self.assertTrue(any('main.py' in p for p in problems))
        self.assertTrue(any('setup_dependencies.json' in p for p in problems))

    def test_ambiguous_post_never_repeats_on_resume(self):
        def api(path, data=None):
            if path == '/object_info':
                return {'SaveImage': {}}
            if path == '/queue':
                return {}
            raise TimeoutError('response lost')
        with patch.object(self.session, 'api', side_effect=api):
            with self.assertRaises(TimeoutError):
                self.session.generate(self.graph, '57', self.destination, 'image')
        with patch.object(self.session, 'api', side_effect=AssertionError('no second POST')):
            with self.assertRaisesRegex(RuntimeError, 'unresolved'):
                self.session.generate(self.graph, '57', self.destination, 'image')

    def test_finished_job_copies_media_without_deleting_source(self):
        source = self.session.comfy / 'output/test/reference.png'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'png test data')
        calls = []
        def api(path, data=None):
            calls.append(path)
            if path == '/object_info':
                return {'SaveImage': {}}
            if path == '/queue':
                return {}
            if path == '/prompt':
                return {'prompt_id': 'job-1'}
            if path == '/history/job-1':
                return {'job-1': {'outputs': {'57': {'images': [{'filename': 'reference.png', 'subfolder': 'test'}]}}}}
            return {}
        with patch.object(self.session, 'api', side_effect=api):
            result = self.session.generate(self.graph, '57', self.destination, 'image')
        self.assertEqual(result.read_bytes(), source.read_bytes())
        self.assertTrue(source.exists())
        self.assertEqual(calls.count('/prompt'), 1)
        self.assertIn('/free', calls)

    def test_failed_job_preserves_id_and_does_not_resubmit(self):
        state = self.destination.parent / 'jobs' / (self.destination.name + '.json')
        import hashlib
        key = hashlib.sha256(json.dumps(self.graph, sort_keys=True).encode()).hexdigest()
        cast.save(state, {'key': key, 'prompt_id': 'failed-job'})
        with patch.object(self.session, 'api', return_value={
            'failed-job': {'status': {'status_str': 'error'}, 'outputs': {}}}) as api:
            with self.assertRaisesRegex(RuntimeError, 'job failed'):
                self.session.generate(self.graph, '57', self.destination, 'image')
        self.assertEqual(api.call_args.args[0], '/history/failed-job')
        self.assertEqual(json.loads(state.read_text())['prompt_id'], 'failed-job')

    def test_stop_is_checked_while_polling(self):
        checks = []
        def cancel():
            checks.append(True)
            if len(checks) > 1:
                raise RuntimeError('Stopped.')
        self.session.check = cancel
        def api(path, data=None):
            if path == '/object_info':
                return {'SaveImage': {}}
            if path == '/queue':
                return {}
            if path == '/prompt':
                return {'prompt_id': 'pending'}
            return {}
        with patch.object(self.session, 'api', side_effect=api), patch.object(cast.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Stopped.'):
                self.session.generate(self.graph, '57', self.destination, 'image')

    def test_h3_uses_reference_without_requiring_a_voice_model(self):
        graph = {key: {'inputs': {}} for key in ('137', '136', '132', '138', '129', '92', '141')}
        graph['136']['inputs']['ref_audios.ref_audio_0'] = ['141', 0]
        with patch.object(cast, 'workflow', return_value=graph):
            result, save_id = cast.video_workflow(self.root, 'Open the notebook.', 'ref.png', '9:16', 'test')
        self.assertEqual(save_id, '92')
        self.assertEqual(result['132']['inputs']['value'], 8)
        self.assertNotIn('141', result)
        self.assertNotIn('ref_audios.ref_audio_0', result['136']['inputs'])
        self.assertIn('no speaking or lip-sync', result['138']['inputs']['value'])

    def gui_method(self, name):
        # Exercise GUI dispatch without creating a desktop or importing Tk at test time.
        tree = ast.parse(Path(__file__).with_name('studio_gui.py').read_text(encoding='utf-8'))
        studio = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Studio')
        method = next(node for node in studio.body if isinstance(node, ast.FunctionDef) and node.name == name)
        namespace = {'CASTWORKSHOP': cast.CASTWORKSHOP, 'scriptforge_prompt': lambda: 'Script instructions'}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'studio_gui.py', 'exec'), namespace)
        return namespace[name]

    def test_auto_make_video_routes_to_castworkshop_without_an_agent(self):
        gui = SimpleNamespace(settings={'animation_provider': cast.CASTWORKSHOP},
                              _make_video_castworkshop=lambda: 'castworkshop route')
        self.assertEqual(self.gui_method('make_video')(gui), 'castworkshop route')

    def test_fifteen_second_script_option_does_not_request_sixty_seconds(self):
        captured = []
        gui = SimpleNamespace(s={'niche_main': 'habits', 'niche_sub': 'discipline'},
                              opt_len=SimpleNamespace(get=lambda: 'Shorts 15s test'), SCRIPT_FORMAT='Output format',
                              _script_request=lambda *args, **kwargs: captured.append((args, kwargs)))
        self.gui_method('write_script')(gui, {'title': 'One small habit', 'hook': 'Start now'})
        args, kwargs = captured[0]
        self.assertIn('15-second', args[0])
        self.assertNotIn('60 seconds', args[0])
        self.assertEqual(args[3], 35)
        self.assertTrue(kwargs['new_video'])


if __name__ == '__main__':
    unittest.main()
