import json
import os
from pathlib import Path
import tempfile
import unittest

from portable_paths import local_environment, migrate_legacy


class PortablePathsTests(unittest.TestCase):
    def test_migration_rebases_media_and_preserves_existing_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root, old = Path(temp) / 'folder with spaces', Path(temp) / 'old'
            root.mkdir(); old.mkdir()
            (root / 'settings.json').write_text('{"keep":true}')
            (old / 'settings.json').write_text('{"keep":false}')
            work = old / 'work' / 'video'
            work.mkdir(parents=True)
            (work / 'project.json').write_text(json.dumps({'voice': str(work / 'voice.mp3')}))
            (work / 'voice.mp3').write_bytes(b'audio')
            self.assertEqual(migrate_legacy(root, old), 2)
            self.assertEqual(json.loads((root / 'settings.json').read_text()), {'keep': True})
            migrated = json.loads((root / 'work/video/project.json').read_text())
            self.assertEqual(migrated['voice'], str(root / 'work/video/voice.mp3'))
            self.assertTrue((work / 'voice.mp3').exists())
            self.assertEqual(migrate_legacy(root, old), 0)

    def test_environment_is_local_and_does_not_change_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            base = {'PATH': 'existing-tools', 'USERPROFILE': 'original-profile'}
            before = dict(os.environ)
            env = local_environment(temp, base)
            self.assertEqual(base['USERPROFILE'], 'original-profile')
            self.assertEqual(dict(os.environ), before)
            for key in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'GEMINI_CLI_HOME',
                        'TEMP', 'HF_HOME', 'npm_config_prefix', 'PLAYWRIGHT_BROWSERS_PATH'):
                self.assertTrue(Path(env[key]).is_relative_to(Path(temp).resolve()))
            self.assertIn('existing-tools', env['PATH'])


if __name__ == '__main__':
    unittest.main()
