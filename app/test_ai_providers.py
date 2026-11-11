import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import io
import urllib.error
from ai_providers import EventStream, agent_command, run_agent, portable_prompt, cli_command, load_env_file, gemini_api_text


class ProviderTests(unittest.TestCase):
    @patch('ai_providers.cli_command', return_value=['codex.exe'])
    def test_windows_animation_sets_workspace_trust_and_preserves_sandbox_choice(self, _):
        with tempfile.TemporaryDirectory() as folder, patch('ai_providers.os.name', 'nt'):
            root = Path(folder)
            cmd = agent_command('OpenAI (Codex)', animation=True, workspace=folder,
                                env={'CODEX_HOME': folder})
            self.assertIn('--no-daemon', cmd)
            self.assertIn('windows.sandbox="unelevated"', cmd)
            self.assertTrue(any('trust_level="trusted"' in value for value in cmd))
            self.assertIn('workspace-write', cmd)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', cmd)
            (root / 'config.toml').write_text('[windows]\nsandbox="elevated"\n')
            cmd = agent_command('OpenAI (Codex)', animation=True, workspace=folder,
                                env={'CODEX_HOME': folder})
            self.assertNotIn('windows.sandbox="unelevated"', cmd)

    @patch('ai_providers.shutil.which', return_value='C:/Users/test/AppData/Local/OpenAI/Codex/bin/build/codex.exe')
    def test_desktop_codex_requires_standalone_install(self, _):
        with self.assertRaisesRegex(RuntimeError, 'standalone'):
            cli_command('OpenAI (Codex)')

    @patch('ai_providers.cli_command', return_value=['codex.exe'])
    def test_blocked_animation_is_failure_even_with_zero_exit(self, _):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'SKILL.md').write_text('skill')
            def run(cmd, **kw):
                kw['on_line'](json.dumps({'type': 'item.completed', 'item': {
                    'type': 'agent_message', 'text': 'Pass 1 is blocked. The session is read-only filesystem access.'}}))
                return 0
            with self.assertRaisesRegex(RuntimeError, 'stopped before later passes'):
                run_agent('OpenAI (Codex)', 'animate', run, cwd=folder, animation=True, skill_dir=folder)

    @patch('ai_providers.cli_command', return_value=['codex.exe'])
    def test_codex_permissions_and_stdin(self, _):
        cmd = agent_command('OpenAI (Codex)', animation=False)
        self.assertIn('read-only', cmd)
        self.assertEqual(cmd[-1], '-')
        cmd = agent_command('OpenAI (Codex)', animation=True, full_auto=True)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', cmd)
        self.assertIn('workspace-write', cmd)

    @patch('ai_providers.cli_command', return_value=['node', 'gemini.js'])
    def test_gemini_permissions(self, _):
        self.assertIn('plan', agent_command('Gemini'))
        self.assertIn('auto_edit', agent_command('Gemini', animation=True))
        self.assertIn('yolo', agent_command('Gemini', animation=True, full_auto=True))

    def test_codex_tools_and_final_answer(self):
        stream = EventStream('OpenAI (Codex)')
        events = stream.feed(json.dumps({'type': 'item.started', 'item': {
            'type': 'command_execution', 'command': 'node render.mjs'}}))
        self.assertEqual(events[0][0], 'tool')
        for text in ('Working...', 'FINAL_VIDEO: C:/test.mp4'):
            stream.feed(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': text}}))
        self.assertEqual(stream.text, 'FINAL_VIDEO: C:/test.mp4')

    def test_gemini_streaming_and_error(self):
        stream = EventStream('Gemini')
        for text in ('hello ', 'world'):
            stream.feed(json.dumps({'type': 'message', 'role': 'assistant', 'delta': True, 'content': text}))
        self.assertEqual(stream.text, 'hello world')
        stream.feed(json.dumps({'type': 'result', 'status': 'error', 'error': {'message': 'quota'}}))
        self.assertIn('quota', stream.error)

    @patch('ai_providers.cli_command', return_value=['codex.exe'])
    def test_nonzero_exit_rejects_partial_answer(self, _):
        def run(cmd, **kw):
            kw['on_line'](json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'partial'}}))
            return 1
        with self.assertRaisesRegex(RuntimeError, 'exit 1'):
            run_agent('OpenAI (Codex)', 'test', run, cwd='.')

    def test_animation_includes_portable_skill_and_no_publish(self):
        prompt = portable_prompt('make a video', 'C:/skills/make-2d-video', True)
        self.assertIn('SKILL.md', prompt)
        self.assertIn('Do not upload or publish', prompt)
        self.assertIn('Do not invoke Claude', prompt)

    def test_npm_entrypoint_comes_from_package_metadata(self):
        with tempfile.TemporaryDirectory(prefix='studio path ') as folder:
            root = Path(folder)
            package = root / 'node_modules/@google/gemini-cli'
            (package / 'bundle').mkdir(parents=True)
            (package / 'bundle/gemini.js').write_text('// test')
            (package / 'package.json').write_text(json.dumps({'bin': {'gemini': 'bundle/gemini.js'}}))
            with patch('ai_providers.shutil.which', side_effect=lambda name, **kw:
                       str(root / 'gemini.cmd') if name == 'gemini' else 'node.exe'):
                self.assertEqual(cli_command('Gemini'), ['node.exe', str(package / 'bundle/gemini.js')])

    @patch('ai_providers.cli_command', return_value=['node', 'gemini.js'])
    def test_missing_auth_diagnostic_is_reported(self, _):
        def run(cmd, **kw):
            kw['on_line']('Please set an Auth method or GEMINI_API_KEY')
            return 41
        with self.assertRaisesRegex(RuntimeError, 'Auth method'):
            run_agent('Gemini', 'test', run, cwd='.')

    @patch('ai_providers.cli_command', return_value=['node', 'gemini.js'])
    def test_rejected_google_login_points_to_gemini_api(self, _):
        def run(cmd, **kw):
            kw['on_line']('An unexpected critical error occurred:IneligibleTierError: This client is no longer supported')
            return 1
        with self.assertRaisesRegex(RuntimeError, 'choose "Gemini API"'):
            run_agent('Gemini', 'test', run, cwd='.')

    @staticmethod
    def _reply(body):
        class Reply(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return Reply(json.dumps(body).encode())

    def test_gemini_api_writes_text_without_a_cli(self):
        seen, events = {}, []
        def opener(request, timeout):
            seen.update(url=request.full_url, key=request.get_header('X-goog-api-key'),
                        body=json.loads(request.data))
            return self._reply({'candidates': [{'content': {'parts': [{'text': 'An idea'}]}}]})
        with patch('ai_providers.urllib.request.urlopen', opener):
            text = run_agent('Gemini API', 'give me ideas', None, cwd='.',
                             env={'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'model-x'},
                             on_event=lambda *e: events.append(e))
        self.assertEqual(text, 'An idea')
        self.assertEqual(events, [('text', 'An idea')])
        self.assertEqual(seen['key'], 'test-key')
        self.assertNotIn('test-key', seen['url'])
        self.assertIn('models/model-x:generateContent', seen['url'])
        self.assertIn('give me ideas', seen['body']['contents'][0]['parts'][0]['text'])

    def test_gemini_api_reports_missing_key_and_api_errors(self):
        with self.assertRaisesRegex(RuntimeError, 'GEMINI_API_KEY'):
            run_agent('Gemini API', 'test', None, cwd='.', env={})
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 404, 'Not Found', {},
                                         io.BytesIO(b'{"error": {"message": "model not found"}}'))
        with patch('ai_providers.urllib.request.urlopen', opener):
            with self.assertRaisesRegex(RuntimeError, r'404.*model not found'):
                gemini_api_text('test', env={'GEMINI_API_KEY': 'k'})

    @patch('ai_providers.cli_command', return_value=['node', 'gemini.js'])
    def test_gemini_api_animates_through_the_gemini_cli(self, _):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'SKILL.md').write_text('skill', encoding='utf-8')
            seen = {}
            def run(cmd, **kw):
                seen['cmd'] = cmd
                kw['on_line'](json.dumps({'type': 'message', 'role': 'assistant', 'content': 'FINAL_VIDEO: a.mp4'}))
                return 0
            env = {'GEMINI_API_KEY': 'k', 'GEMINI_MODEL': 'model-x', 'GEMINI_CLI_HOME': folder}
            text = run_agent('Gemini API', 'animate', run, cwd=folder, animation=True, skill_dir=folder, env=env)
            self.assertEqual(text, 'FINAL_VIDEO: a.mp4')
            self.assertEqual(seen['cmd'][:2], ['node', 'gemini.js'])
            self.assertIn('model-x', seen['cmd'])
            key_home = Path(folder) / 'gemini-api-key'
            self.assertEqual(env['GEMINI_CLI_HOME'], str(key_home))
            self.assertEqual(json.loads((key_home / '.gemini/settings.json').read_text())
                             ['security']['auth']['selectedType'], 'gemini-api-key')
            run_agent('Gemini API', 'animate', run, cwd=folder, animation=True, skill_dir=folder, env=env)
            self.assertEqual(env['GEMINI_CLI_HOME'], str(key_home))
            run_agent('Gemini', 'animate', run, cwd=folder, animation=True, skill_dir=folder, env=env)
            self.assertEqual(env['GEMINI_CLI_HOME'], folder)
            with self.assertRaisesRegex(RuntimeError, 'GEMINI_API_KEY'):
                run_agent('Gemini API', 'animate', run, cwd=folder, animation=True, skill_dir=folder, env={})

    def test_env_file_fills_only_missing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / '.env'
            f.write_text('# keys\nGEMINI_API_KEY="from-file"\n\nGEMINI_MODEL=file-model\n', encoding='utf-8')
            env = load_env_file(f, {'GEMINI_MODEL': 'already-set'})
            self.assertEqual(env, {'GEMINI_MODEL': 'file-model', 'GEMINI_API_KEY': 'from-file'})
            self.assertEqual(load_env_file(Path(folder) / 'missing', {}), {})

    def test_env_file_drops_inherited_model_that_is_not_a_model_name(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / '.env'
            f.write_text('GEMINI_API_KEY=k\nGEMINI_MODEL=\n', encoding='utf-8')
            env = load_env_file(f, {'GEMINI_MODEL': '<model-that-succeeded>'})
            self.assertEqual(env, {'GEMINI_API_KEY': 'k'})
            self.assertEqual(load_env_file(Path(folder) / 'missing', {'GEMINI_MODEL': 'gemini-3.5-flash'}),
                             {'GEMINI_MODEL': 'gemini-3.5-flash'})


if __name__ == '__main__':
    unittest.main()
