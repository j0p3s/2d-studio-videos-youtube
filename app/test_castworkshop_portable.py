"""Offline verification of the optional portable integration's copy boundaries."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('cast_portable', Path(__file__).resolve().parents[1] /
                                            'integrations/castworkshop/portable.py')
portable = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(portable)


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.bin'
        self.source.write_bytes(b'model bytes')
        self.target = self.root / 'package/models/model.bin'

    def test_copy_verified_keeps_source_and_reuses_identical_target(self):
        portable.copy_verified(self.source, self.target)
        self.assertEqual(self.source.read_bytes(), self.target.read_bytes())
        with patch.object(portable.shutil, 'copy2', side_effect=AssertionError('must reuse')):
            portable.copy_verified(self.source, self.target)

    def test_conflicting_target_is_never_overwritten(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'private previous data')
        with self.assertRaisesRegex(RuntimeError, 'preserved both'):
            portable.copy_verified(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b'private previous data')
        self.assertTrue(self.source.exists())

    def test_remaining_space_reuses_manually_copied_files(self):
        folder = self.root / 'source'
        folder.mkdir()
        (folder / 'existing.bin').write_bytes(b'already copied')
        (folder / 'missing.bin').write_bytes(b'new data')
        destination = self.root / 'destination'
        destination.mkdir()
        (destination / 'existing.bin').write_bytes(b'already copied')
        self.assertEqual(portable.additional_bytes(folder, destination), len(b'new data'))

    def test_generated_tts_settings_cache_is_not_read_or_copied(self):
        folder = self.root / 'original/tts_audio_suite/utils/audio'
        folder.mkdir(parents=True)
        cache = folder / '.inline_tag_settings_cache.json'
        cache.write_text('generated settings')
        (folder / 'required.py').write_text('required code')
        target = self.root / 'destination'
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path == cache:
                raise PermissionError('unreadable cache')
            return original_open(path, *args, **kwargs)

        with patch.object(portable, 'ROOT', self.root), patch.object(Path, 'open', guarded_open):
            self.assertEqual(portable.additional_bytes(folder, target), len(b'required code'))
            portable.copy_tree(folder, target)
            portable.verify_tree(folder, target)
        self.assertFalse((target / cache.name).exists())
        self.assertTrue((target / 'required.py').exists())
        self.assertFalse(portable.disposable(self.root / cache.name))

    def test_required_file_permission_errors_still_stop_import(self):
        folder = self.root / 'original'
        folder.mkdir()
        (folder / 'required.py').write_text('required code')
        with patch.object(portable, 'digest', side_effect=PermissionError('required file denied')):
            with self.assertRaises(PermissionError):
                portable.copy_tree(folder, self.root / 'destination')

    def test_cleanup_rejects_an_arbitrary_source_without_deleting(self):
        with patch.object(portable.shutil, 'rmtree', side_effect=AssertionError('must not delete')):
            with self.assertRaisesRegex(RuntimeError, 'restricted'):
                portable.retire_source(self.root)

    def test_verify_tree_blocks_missing_or_corrupt_files(self):
        folder = self.root / 'original'
        folder.mkdir()
        (folder / 'file.bin').write_bytes(b'original')
        destination = self.root / 'destination'
        destination.mkdir()
        with patch.object(portable, 'ROOT', self.root):
            with self.assertRaisesRegex(RuntimeError, 'missing or different'):
                portable.verify_tree(folder, destination)
            (destination / 'file.bin').write_bytes(b'corrupt!')
            with self.assertRaisesRegex(RuntimeError, 'missing or different'):
                portable.verify_tree(folder, destination)
            (destination / 'file.bin').write_bytes(b'original')
            portable.verify_tree(folder, destination)

    def test_corrupted_copy_is_not_committed(self):
        def corrupt(source, target):
            target.write_bytes(b'corrupted')
        with patch.object(portable.shutil, 'copy2', side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, 'verification failed'):
                portable.copy_verified(self.source, self.target)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.source.exists())

    def test_incomplete_source_blocks_import_before_copying(self):
        with patch.object(portable, 'inventory', return_value=([self.source], [], True)), \
             patch.object(portable, 'copy_tree', side_effect=AssertionError('must not copy')):
            with self.assertRaisesRegex(RuntimeError, 'Finish downloads'):
                portable.package(self.root)

    def test_active_installation_blocks_import(self):
        with patch.object(portable, 'inventory', return_value=([], [123], True)):
            with self.assertRaisesRegex(RuntimeError, 'close source processes'):
                portable.package(self.root)

    def test_manifest_missing_model_is_rejected(self):
        folder = self.root / 'CastWorkshop/config'
        folder.mkdir(parents=True)
        (folder / 'setup_dependencies.json').write_text(json.dumps({'assets': [
            {'name': 'missing', 'destination': 'vae/missing.bin', 'size': 5, 'sha256': '0'*64}]}))
        with self.assertRaisesRegex(RuntimeError, 'missing or incomplete'):
            portable.verify_assets(self.root)

    def test_environment_uses_current_package_location(self):
        with patch.object(portable, 'ROOT', self.root / 'relocated package'):
            env = portable.environment()
            self.assertEqual(env['COMFY_PYTHON'], str(portable.python_path('comfy')))
            self.assertTrue(Path(env['HF_HOME']).is_relative_to(portable.ROOT))
            self.assertNotIn('PYTHONHOME', env)

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows directory junctions')
    def test_junction_creation_and_refresh_after_relocation(self):
        package = self.root / 'package with spaces'
        with patch.object(portable, 'ROOT', package):
            link = package / 'apps/ComfyUI/models'
            link.parent.mkdir(parents=True)
            target = package / 'models/comfyui'
            portable.junction(link, target)
            self.assertEqual(link.resolve(), target.resolve())
        moved = self.root / 'moved package'
        package.rename(moved)
        with patch.object(portable, 'ROOT', moved):
            link = moved / 'apps/ComfyUI/models'
            target = moved / 'models/comfyui'
            try:
                portable.junction(link, target)
                self.assertEqual(link.resolve(), target.resolve())
            finally:
                if link.is_junction():
                    link.rmdir()


if __name__ == '__main__':
    unittest.main()
