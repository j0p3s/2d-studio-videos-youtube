import asyncio
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from studio_gui import Studio


class VoiceRecoveryTests(unittest.TestCase):
    def exercise(self, root, save):
        text = ('A sentence about discipline and taking a small step. ' * 28).strip()
        chunks = Studio._speech_chunks(text)
        cache = root / 'voice_parts'
        cache.mkdir()
        key = lambda t: hashlib.sha256(('en-US-AndrewMultilingualNeural\n+0%\n' + t).encode()).hexdigest()[:24]
        cached = cache / (key(chunks[0]) + '.mp3')
        cached.write_bytes(b'existing-audio')
        app = SimpleNamespace(_cancel=False, VOICE_WORKERS=3, _speech_chunks=Studio._speech_chunks,
                              check_cancel=lambda: None, prog=lambda *args: None)
        def join(files, out):
            out.write_bytes(b''.join(p.read_bytes() for p in files))
            return out
        app._join_mp3 = join
        class Communicate:
            def __init__(self, text, **kwargs):
                self.text = text
            async def save(self, path):
                return await save(self.text, Path(path))
        async def no_sleep(*args):
            pass
        with patch('edge_tts.Communicate', Communicate), patch('asyncio.sleep', no_sleep):
            out = Studio._make_voice_edge(app, text, root, root / 'voice.mp3',
                                         'en-US-AndrewMultilingualNeural', 0)
        self.assertEqual(cached.read_bytes(), b'existing-audio')
        return out

    def test_failed_long_passage_recovers_in_pieces_without_revoicing_cache(self):
        seen = []
        async def save(text, path):
            seen.append(text)
            if len(text) > 450:
                raise RuntimeError('No audio received')
            path.write_bytes(text.encode())
        with tempfile.TemporaryDirectory() as temp:
            out = self.exercise(Path(temp), save)
            self.assertTrue(out.read_bytes().startswith(b'existing-audio'))
            self.assertTrue(any(len(text) <= 450 for text in seen))
            self.assertFalse(list(Path(temp).rglob('*.partial.mp3')))

    def test_service_outage_does_not_publish_partial_voiceover(self):
        async def save(text, path):
            path.write_bytes(b'incomplete')
            raise RuntimeError('No audio received')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(RuntimeError, 'Completed passages'):
                self.exercise(root, save)
            self.assertFalse((root / 'voice.mp3').exists())
            self.assertFalse(list(root.rglob('*.partial.mp3')))
            self.assertEqual(len(list((root / 'voice_parts').glob('*.mp3'))), 1)


if __name__ == '__main__':
    unittest.main()
