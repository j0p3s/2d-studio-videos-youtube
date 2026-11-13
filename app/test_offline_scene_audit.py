import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from host_render import HostAnimation
from check_offline_scenes import accept_repair, check_project


class OfflineSceneAuditTests(unittest.TestCase):
    def result(self, motion=.001, errors=None):
        return {'id':'s001','motion_ratio':motion,'color_spread':40,
                'runtime_errors':errors or [],'missing':False,'issues':['Little motion']}

    def test_repair_must_improve_flagged_motion_without_adding_runtime_errors(self):
        before = self.result()
        self.assertFalse(accept_repair(before,self.result(.001)))
        self.assertFalse(accept_repair(before,self.result(.2,['Broken pose'])))
        self.assertTrue(accept_repair(before,self.result(.2)))
        self.assertTrue(accept_repair(self.result(errors=['Broken pose']),self.result()))

    def fixture(self, folder, manual=False):
        root=Path(folder); p=root/'projects/video'
        (p/'story').mkdir(parents=True); (p/'scenes/shots').mkdir(parents=True); (p/'build').mkdir()
        (p/'story/shots.json').write_text(json.dumps({'shots':[{'id':'s001','scene':'Original'}]}))
        (p/'build/local_animation.json').write_text(json.dumps({'complete':{'s001':{'manual':manual}}}))
        source=p/'scenes/shots/s001.js';source.write_text('original source')
        host=HostAnimation(root,'video','python',lambda cmd:(0,''),None,lambda:None)
        return host,source

    def test_unimproved_replacement_is_rolled_back_and_original_is_backed_up(self):
        with tempfile.TemporaryDirectory() as folder:
            host, source=self.fixture(folder)
            response=json.dumps({'scene':'Writes a note','code':"registerShot('s001',{draw(){}})"})
            report={'shots':[self.result()]}
            with patch('check_offline_scenes.audit',return_value=report):
                result=check_project(host,request=lambda *args,**kwargs:response,log=lambda _:None)
            self.assertEqual(source.read_text(),'original source')
            self.assertEqual(result['decisions'][0]['status'],'reverted_no_measured_improvement')
            self.assertFalse(result['visually_approved'])
            self.assertEqual(len(list((host.project/'build/scene_audit/backups').glob('*/s001.js'))),1)

    def test_approved_manual_scenes_are_not_rewritten(self):
        with tempfile.TemporaryDirectory() as folder:
            host,source=self.fixture(folder,manual=True)
            with patch('check_offline_scenes.audit',return_value={'shots':[self.result()]}), \
                    patch('builtins.print'), patch('local_animation.ollama_provider.text') as model:
                result=check_project(host,request=lambda *args,**kwargs: self.fail('Manual scene was rewritten'))
            self.assertEqual(source.read_text(),'original source')
            self.assertEqual(result['decisions'][0]['status'],'manual_scene_preserved')
            model.assert_not_called()

    def test_browser_failure_after_repair_restores_original(self):
        with tempfile.TemporaryDirectory() as folder:
            host,source=self.fixture(folder)
            response=json.dumps({'scene':'Writes a note','code':"registerShot('s001',{draw(){}})"})
            with patch('check_offline_scenes.audit',side_effect=[{'shots':[self.result()]},RuntimeError('Browser failed')]):
                with self.assertRaisesRegex(RuntimeError,'Browser failed'):
                    check_project(host,request=lambda *args,**kwargs:response,log=lambda _:None)
            self.assertEqual(source.read_text(),'original source')
