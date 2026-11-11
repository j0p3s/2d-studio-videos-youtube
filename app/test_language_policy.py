import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from language_policy import ENGLISH_VOICES, english_voice, narration_hash, migrate_speech_settings
from studio_gui import Studio


class EnglishPipelineTests(unittest.TestCase):
    def test_auto_does_not_reuse_saved_portuguese_media(self):
        settings = {'voice': 'pt-PT-DuarteNeural', 'engine': 'ElevenLabs', 'current': {
            'lang': 'pt', 'voice': 'old.mp3', 'video': 'old.mp4', 'thumb': 'old.png', 'script': 'Começa pequeno.'}}
        result = migrate_speech_settings(settings)
        self.assertNotIn('voice', result['current'])
        self.assertNotIn('video', result['current'])
        self.assertEqual(result['current']['script'], 'Começa pequeno.')
        self.assertEqual(result['engine'], 'Piper (offline)')
        self.assertEqual(migrate_speech_settings({'engine': 'Free (Edge)'})['engine'], 'Piper (offline)')
        chosen = migrate_speech_settings({'engine': 'Free (Edge)', 'piper_default': True})
        self.assertEqual(chosen['engine'], 'Free (Edge)')

    def test_saved_portuguese_voice_is_replaced(self):
        self.assertEqual(english_voice('pt-PT-DuarteNeural'), 'en-US-AndrewMultilingualNeural')
        self.assertEqual(english_voice('en-GB-RyanNeural'), 'en-GB-RyanNeural')
        self.assertTrue(all(v.startswith('en-') and v.endswith('Neural') for v in ENGLISH_VOICES))

    def test_portuguese_revision_stays_english_for_claude(self):
        native = Mock(return_value='English script')
        app = SimpleNamespace(settings={}, ask_claude=native)
        Studio.ask_ai(app, 'Reescreve este guião em português')
        prompt = native.call_args.args[0]
        self.assertIn('MANDATORY OUTPUT LANGUAGE: English', prompt)
        self.assertTrue(prompt.endswith('This language requirement also applies to revisions.'))

    def test_codex_and_gemini_receive_same_english_policy(self):
        for provider in ('OpenAI (Codex)', 'Gemini'):
            app = SimpleNamespace(settings={'animation_provider': provider}, prog=Mock(), run_cmd=Mock())
            with patch('studio_gui.run_agent', return_value='FINAL_VIDEO: test.mp4') as run:
                Studio.ask_ai(app, 'Legendas em português', tools=['Read'])
                prompt = run.call_args.args[1]
                self.assertIn('captions matching the English narration', prompt)
                self.assertIn('--lang en', prompt)

    def test_edited_portuguese_narration_translated_before_microsoft_speech(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            app = SimpleNamespace(
                _save_narration=lambda: ('Começa pequeno.', folder),
                opt_voice=SimpleNamespace(get=lambda: 'pt-PT-DuarteNeural', set=Mock()),
                sld_rate=SimpleNamespace(get=lambda: -5), settings={'engine': 'ElevenLabs'},
                s={'narration_en_hash': narration_hash('Older narration')},
                ask_ai=Mock(return_value='Start small.'), check_cancel=Mock(),
                _make_voice_edge=Mock(return_value=folder / 'voiceover.mp3'),
                txt_narr=SimpleNamespace(delete=Mock(), insert=Mock()),
                save_state=Mock(), _sync_voice_page=Mock(),
                run_job=lambda label, work, done: done(work()))
            Studio.make_voice(app)
            self.assertEqual(app._make_voice_edge.call_args.args[0], 'Start small.')
            self.assertEqual(app._make_voice_edge.call_args.args[3], 'en-US-AndrewMultilingualNeural')
            self.assertEqual(app.settings['engine'], 'Free (Edge)')
            self.assertEqual(app.s['lang'], 'en')
            self.assertEqual((folder / 'script.txt').read_text(), 'Start small.\n')


if __name__ == '__main__':
    unittest.main()
