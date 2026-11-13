import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline_report import write_report
from check_offline_scenes import main


class OfflineReportTests(unittest.TestCase):
    def test_regeneration_replaces_previous_run_and_both_entry_points(self):
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'report'
            write_report(report,[{'name':'OLD PROJECT','path':folder,'status':'failed','error':'old failure'}],started=1,finished=True)
            write_report(report,[],started=2,finished=True)
            text=(report/'index.html').read_text(encoding='utf-8')
            self.assertNotIn('OLD PROJECT',text)
            self.assertNotIn('old failure',text)
            self.assertIn('No offline projects found',text)
            self.assertEqual((report/'.index.html').read_bytes(),(report/'index.html').read_bytes())

    def test_untrusted_names_findings_and_errors_are_escaped(self):
        with tempfile.TemporaryDirectory() as folder:
            record={'name':'<script>alert(1)</script>','path':folder,'status':'failed',
                    'error':'<img src=x onerror=alert(1)>','audit':{'shots':[
                        {'id':'<b>s001</b>','issues':['<iframe>'],'images':[]}],
                        'decisions':[{'id':'<b>s001</b>','status':'repair_failed','detail':'<script>bad</script>'}]}}
            p=write_report(folder,[record],started=1,finished=True)
            text=p.read_text(encoding='utf-8')
            self.assertNotIn('<script>',text)
            self.assertNotIn('<iframe>',text)
            self.assertIn('&lt;script&gt;',text)
            self.assertIn('Repair failed; original kept',text)

    def test_only_preview_images_inside_the_project_audit_folder_are_copied(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=root/'project';images=project/'build/scene_audit'
            images.mkdir(parents=True)
            inside=images/'s001.png';inside.write_bytes(b'image')
            outside=root/'private.png';outside.write_bytes(b'private')
            record={'name':'Video','path':str(project),'status':'complete','audit':{'shots':[
                {'id':'s001','issues':[],'images':[str(inside),str(outside)],'sample_times':[.5,1.5]}]}}
            p=write_report(root/'report',[record],started=1,finished=True)
            assets=list((root/'report/assets').iterdir())
            self.assertEqual(len(assets),1)
            self.assertEqual(assets[0].read_bytes(),b'image')
            self.assertIn('Technical checks clear',p.read_text(encoding='utf-8'))
            self.assertIn('Visual review required',p.read_text(encoding='utf-8'))
            self.assertNotIn('>Passed<',p.read_text(encoding='utf-8'))

    def test_fatal_setup_error_has_fresh_report_instead_of_empty_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);report=root/'report'
            args=['checker','--all','--studio',str(root/'missing-studio'),'--report-dir',str(report)]
            with patch('sys.argv',args),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(SystemExit,'projects folder not found'):
                    main()
            text=(report/'.index.html').read_text(encoding='utf-8')
            self.assertIn('Check stopped',text)
            self.assertIn('projects folder not found',text)
            self.assertNotIn('<h2>No offline projects found</h2>',text)

    def test_old_audit_is_not_presented_when_new_project_check_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);studio=root/'studio';project=studio/'projects/video'
            audit_file=project/'build/scene_audit/report.json';audit_file.parent.mkdir(parents=True)
            audit_file.write_text(json.dumps({'shots':[{'id':'STALE_SCENE','issues':[],'images':[]}]}))
            os.utime(audit_file,(1,1))
            report=root/'report'
            args=['checker','--project','projects/video','--studio',str(studio),'--report-dir',str(report)]
            with patch('sys.argv',args),patch('check_offline_scenes.check_project',side_effect=RuntimeError('new failure')),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(SystemExit,'Failed projects'):
                    main()
            text=(report/'index.html').read_text(encoding='utf-8')
            self.assertIn('new failure',text)
            self.assertNotIn('STALE_SCENE',text)

    def test_current_audit_findings_survive_a_stop_for_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);studio=root/'studio';project=studio/'projects/video'
            project.mkdir(parents=True)
            def stopped(*args,**kwargs):
                file=project/'build/scene_audit/report.json';file.parent.mkdir(parents=True)
                file.write_text(json.dumps({'shots':[{'id':'s001','issues':['Low residual motion'],'images':[]}]}))
                raise RuntimeError('Needs review')
            args=['checker','--project','projects/video','--studio',str(studio),'--report-dir',str(root/'report')]
            with patch('sys.argv',args),patch('check_offline_scenes.check_project',side_effect=stopped),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
            text=(root/'report/index.html').read_text(encoding='utf-8')
            self.assertIn('Low residual motion',text)
            self.assertIn('Needs review',text)


if __name__=='__main__':
    unittest.main()
