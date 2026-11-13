"""Offline regression checks for saved ComfyUI jobs lost after a restart."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_launcher as launcher


class RecoveryTests(unittest.TestCase):
    def test_missing_job_is_backed_up_before_one_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state = folder / 'final-state.json'
            launcher.save_state(state, {'prompt_id': 'lost'})
            submissions = []

            def api(path, data=None):
                if path == '/object_info':
                    return {'SaveVideo': {}}
                if path == '/prompt':
                    submissions.append(data)
                    return {'prompt_id': 'replacement'}
                return {}

            with patch.object(launcher, 'SERVER_PROCESS', None), \
                 patch.object(launcher, 'api', side_effect=api), \
                 patch.object(launcher.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'No replacement was submitted'):
                    launcher.stage('final', {'1': {'class_type': 'SaveVideo'}}, '1', folder)
            self.assertEqual(len(submissions), 1)
            self.assertEqual(json.loads(state.read_text())['prompt_id'], 'replacement')
            backups = list(folder.glob('final-state-lost-*.json'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text()), {'prompt_id': 'lost'})

    def test_other_active_job_prevents_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state = folder / 'final-state.json'
            launcher.save_state(state, {'prompt_id': 'lost'})

            def api(path, data=None):
                if path == '/queue':
                    return {'queue_running': [[1, 'someone-else']]}
                if path.startswith('/history/'):
                    return {}
                self.fail('Must not submit while queue is busy')

            with patch.object(launcher, 'SERVER_PROCESS', None), \
                 patch.object(launcher, 'api', side_effect=api), \
                 patch.object(launcher.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'No replacement was submitted'):
                    launcher.stage('final', {}, '1', folder)
            self.assertEqual(json.loads(state.read_text()), {'prompt_id': 'lost'})

    def test_completion_between_history_and_queue_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            launcher.save_state(folder / 'final-state.json', {'prompt_id': 'job'})
            completed = {'job': {'status': {'status_str': 'error'}}}
            responses = [{}, {}, {}, {}, {}, {}, completed, completed]
            with patch.object(launcher, 'SERVER_PROCESS', None), \
                 patch.object(launcher, 'api', side_effect=responses) as api, \
                 patch.object(launcher.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'final failed'):
                    launcher.stage('final', {}, '1', folder)
            self.assertFalse(any(call.args[0] == '/prompt' for call in api.call_args_list))


if __name__ == '__main__':
    unittest.main()
