"""Audit offline projects; optionally repair flagged scenes with the selected local model.

python app/check_offline_scenes.py --all --repair
python app/check_offline_scenes.py --project projects/my-video --repair --export
No cloud calls. Existing manual/approved scenes are audited but never auto-rewritten.
Each CLI run rebuilds reports/offline-animations/{.index.html,index.html}; --report-dir
overrides that folder. The Windows launcher also offers to open the completed report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def audit(host):
    output = host.invoke(['node', str(Path(__file__).with_name('offline_scene_audit.mjs')),
                          str(host.studio), str(host.project)])
    marker = 'OFFLINE_AUDIT_JSON:'
    for line in output.splitlines():
        if line.startswith(marker):
            result = json.loads(line[len(marker):])
            if result.get('page_errors'):
                raise RuntimeError('Scene audit page errors: ' + '\n'.join(result['page_errors']))
            return result
    raise RuntimeError('Scene auditor returned no report')


def accept_repair(before, after):
    if after['runtime_errors'] or after['missing'] or after.get('issues'):
        return False
    # Clear the thresholds, not just a tiny relative gain. Also reject regressions
    # in a previously healthy measurement when repairing a different problem.
    if after['motion_ratio'] < .008:
        return False
    if after['color_spread'] < 9:
        return False
    return True


def check_project(host, *, request=None, log=print):
    from local_animation import SCENE_GUIDE, scene_result, normalize_source, save_json
    p = host.project
    before = audit(host)
    plan_file, checkpoint = p / 'story/shots.json', p / 'build/local_animation.json'
    story = json.loads(plan_file.read_text(encoding='utf-8'))
    saved = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {}
    complete = saved.setdefault('complete', {})
    by_id = {s['id']: s for s in story['shots']}
    originals, decisions = {}, []
    batch = str(time.time_ns())
    for result in before['shots']:
        if not result['issues']:
            continue
        sid = result['id']
        if not sid.replace('_', '').replace('-', '').isalnum():
            raise RuntimeError('Invalid shot ID in audit')
        log(sid + ': ' + '; '.join(result['issues']))
        if complete.get(sid, {}).get('manual'):
            decisions.append({'id': sid, 'status': 'manual_scene_preserved'})
            continue
        if request is None:
            decisions.append({'id': sid, 'status': 'review_required'})
            continue
        host.check_cancel()
        target = p / 'scenes/shots' / (sid + '.js')
        original = target.read_bytes() if target.exists() else None
        source = original.decode('utf-8') if original else ''
        backup = p / 'build/scene_audit/backups' / batch / (sid + '.js')
        if original is not None:
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(original)
        prompt = (SCENE_GUIDE + '\nRepair the concrete audit findings below. Preserve the narrator, '
                  'shot ID/timing, character design, location and meaningful action. Improve physical '
                  'posing, contact, framing and anticipation/action/settle. Do not add unrelated props '
                  'or make a character slide offscreen. Camera drift alone does not count as acting.\n'
                  'Shot: ' + json.dumps(by_id[sid]) + '\nStoryboard: ' +
                  json.dumps(saved.get('directions', {}).get(sid, {})) + '\nAudit: ' +
                  json.dumps(result['issues']) + '\nPrevious source:\n' + source[:18000])
        try:
            description, code = scene_result(request(prompt, repair=True), sid)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix('.audit.mjs')
            try:
                temp.write_text(code, encoding='utf-8')
                try:
                    host.invoke(['node', '--check', str(temp)])
                except RuntimeError:
                    code = normalize_source(code)
                    temp.write_text(code, encoding='utf-8')
                    host.invoke(['node', '--check', str(temp)])
            finally:
                temp.unlink(missing_ok=True)
            originals[sid] = (original, description, code)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            if str(exc) == 'Stopped.':
                raise
            decisions.append({'id': sid, 'status': 'repair_failed', 'detail': str(exc)[-1200:]})
    try:
        for sid, (_, _, code) in originals.items():
            (p / 'scenes/shots' / (sid + '.js')).write_text(code, encoding='utf-8')
        after = audit(host) if originals else before
    except BaseException:
        # Never leave unverified replacement code behind after cancellation/browser failure.
        for sid, (original, _, _) in originals.items():
            target = p / 'scenes/shots' / (sid + '.js')
            target.write_bytes(original) if original is not None else target.unlink(missing_ok=True)
        raise
    before_by_id = {x['id']: x for x in before['shots']}
    for candidate in after['shots']:
        sid = candidate['id']
        if sid not in originals:
            continue
        original, description, _ = originals[sid]
        target = p / 'scenes/shots' / (sid + '.js')
        if accept_repair(before_by_id[sid], candidate):
            by_id[sid]['scene'] = description
            record = complete.setdefault(sid, {})
            record['hash'] = hashlib.sha256(target.read_bytes()).hexdigest()
            decisions.append({'id': sid, 'status': 'accepted_by_runtime_and_pixel_checks'})
        else:
            target.write_bytes(original) if original is not None else target.unlink(missing_ok=True)
            decisions.append({'id': sid, 'status': 'reverted_no_measured_improvement'})
    save_json(plan_file, story)
    save_json(checkpoint, saved)
    final = audit(host) if any(x['status'].startswith('reverted') for x in decisions) else after
    final['decisions'] = decisions
    final['visually_approved'] = False
    report = p / 'build/scene_audit/report.json'
    save_json(report, final)
    log(f'Scene audit saved: {report}. Human review is still required.')
    blocking = [x['id'] for x in final['shots'] if x['runtime_errors'] or x['missing']]
    if blocking:
        raise RuntimeError('Unresolved scene runtime failures: ' + ', '.join(blocking))
    unresolved = [x['id'] for x in final['shots'] if x['issues'] and
                  not complete.get(x['id'], {}).get('manual')]
    if request is not None and unresolved:
        raise RuntimeError('Scene audit still needs review: ' + ', '.join(unresolved) +
                           '. Original code and the audit report are preserved; final export was not approved.')
    return final


def main():
    from host_render import HostAnimation
    from local_animation import LocalAnimation
    from portable_paths import local_environment
    from ai_providers import load_env_file
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studio', type=Path, default=Path(__file__).resolve().parents[1] / 'growkaz-stickman-studio')
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--all', action='store_true', help='All projects with an offline checkpoint')
    scope.add_argument('--project', type=Path)
    parser.add_argument('--repair', action='store_true', help='Use local Ollama for flagged scenes')
    parser.add_argument('--export', action='store_true', help='Rerender/mix after repairs')
    parser.add_argument('--model', default='')
    parser.add_argument('--report-dir', type=Path, help='HTML report folder (default: reports/offline-animations beside the studio)')
    args = parser.parse_args()
    studio = args.studio.resolve(); root = studio.parent
    from offline_report import write_report
    folder = args.report_dir or root / 'reports/offline-animations'
    started = time.time_ns()
    records, fatal = [], None
    write_report(folder, records, started=started, repair=args.repair, export=args.export)
    try:
        if not studio.is_dir() or not (studio / 'projects').is_dir():
            raise RuntimeError('Studio projects folder not found: ' + str(studio / 'projects'))
        env = local_environment(root); load_env_file(root / '.env', env)
        projects = sorted(p.parent.parent for p in (studio / 'projects').glob('*/build/local_animation.json')
                          if not p.parent.parent.name.startswith('_')) if args.all else [args.project if args.project.is_absolute() else studio / args.project]
        python = root / '.venv/Scripts/python.exe'
        if not python.exists():
            import sys
            python = Path(sys.executable)
        def run(cmd):
            result = subprocess.run(cmd, cwd=studio, env=env, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', creationflags=0x08000000 if __import__('os').name == 'nt' else 0)
            return result.returncode, result.stdout + result.stderr
        for project in projects:
            project = project.resolve()
            record = {'name': project.name, 'path': str(project), 'status': 'checking', 'audit': None}
            records.append(record)
            write_report(folder, records, started=started, repair=args.repair, export=args.export)
            project_started = time.time_ns()
            print('Checking ' + project.name, flush=True)
            try:
                if project.parent != studio / 'projects':
                    raise ValueError('Project must be directly under the studio projects folder')
                model = args.model
                metrics_file = project / 'build/ollama_performance.json'
                if not model and metrics_file.exists():
                    model = json.loads(metrics_file.read_text(encoding='utf-8')).get('model', '')
                local = LocalAnimation(studio, project.name, python, run, env, model, lambda: None, print)
                record['audit'] = check_project(local.host, request=local.request if args.repair else None)
                if args.export:
                    import ollama_provider
                    ollama_provider.release_model(model, env)
                    story = json.loads((project / 'story/shots.json').read_text(encoding='utf-8'))
                    local.host.export(float(story['duration']))
                record['status'] = 'complete'
            except Exception as exc:
                record.update(status='failed', error=str(exc))
                # check_project can save its current findings and then stop for review.
                # Never present an older successful audit as results from a failed new run.
                current_report = project / 'build/scene_audit/report.json'
                if record['audit'] is None:
                    try:
                        if current_report.stat().st_mtime_ns >= project_started:
                            record['audit'] = json.loads(current_report.read_text(encoding='utf-8'))
                    except (OSError, ValueError):
                        pass
                print(str(exc), flush=True)
    except KeyboardInterrupt:
        fatal = 'The check was cancelled. Some projects may not have been checked.'
        if records and records[-1]['status'] == 'checking':
            records[-1].update(status='cancelled', error=fatal)
    except Exception as exc:
        fatal = str(exc)
    finally:
        entry = write_report(folder, records, started=started, finished=True, error=fatal,
                             repair=args.repair, export=args.export)
        print('HTML REPORT: ' + str(entry), flush=True)
    if fatal:
        raise SystemExit(fatal)
    failed = [r['name'] for r in records if r['status'] == 'failed']
    if failed:
        raise SystemExit('Failed projects: ' + ', '.join(failed))


if __name__ == '__main__':
    main()
