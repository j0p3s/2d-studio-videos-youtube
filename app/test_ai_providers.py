import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from ai_providers import EventStream, agent_command, run_agent, portable_prompt, cli_command


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


if __name__ == '__main__':
    unittest.main()
