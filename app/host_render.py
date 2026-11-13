"""App-owned rendering for sandboxed agents; no general command or IPC endpoint."""
import hashlib
import json
import math
from pathlib import Path
import re


class HostAnimation:
    def __init__(self, studio, slug, python, run, ask, check_cancel):
        self.studio = Path(studio).resolve()
        if not slug or Path(slug).name != slug or '/' in slug or '\\' in slug or slug in ('.', '..'):
            raise ValueError('Invalid project name')
        self.project = (self.studio / 'projects' / slug).resolve()
        self.project.relative_to((self.studio / 'projects').resolve())
        self.python, self.run, self.ask, self.check_cancel = python, run, ask, check_cancel

    def invoke(self, cmd, *, render=False):
        self.check_cancel()
        rc, output = self.run(cmd)
        if rc or (render and re.search(r'shot error(?::|\(s\))|\[pageerror\]|BOOT ERROR|shots have no scene file', output, re.I)):
            raise RuntimeError('App rendering failed; saved scene files are preserved.\n' + output[-2400:])
        return output

    def contact_sheets(self, index, count, duration):
        story = json.loads((self.project / 'story' / 'shots.json').read_text(encoding='utf-8'))
        shots = story['shots']
        if not shots:
            raise RuntimeError('The agent did not write a shot plan.')
        final = index == count - 1
        cmd = ['node', 'render.mjs', '--project', str(self.project), '--scale', '0.5']
        if final:
            cmd += ['--sheet']
            folder = self.project / 'build' / 'sheets'
        else:
            build_count = max(1, count - 1)
            lo, hi = round(duration * index / build_count, 2), round(duration * (index + 1) / build_count, 2)
            chosen = [s for s in shots if lo <= float(s['start']) < hi]
            times = [float(s['start']) + (float(s['end']) - float(s['start'])) * .45 for s in chosen]
            if not times or not all(math.isfinite(t) and t >= 0 for t in times):
                raise RuntimeError('No valid shots were found for this pass.')
            cmd += ['--stills', ','.join(f'{t:.3f}' for t in times)]
            folder = self.project / 'build' / 'stills'
        self.invoke(cmd, render=True)
        images = sorted(folder.glob('sheet_*.png'))
        if not images:
            raise RuntimeError('The app renderer produced no contact sheets.')
        return images

    def fingerprint(self):
        digest = hashlib.sha256()
        candidates = [self.project / 'config.json']
        for folder in ('scenes', 'story', 'timeline'):
            candidates.extend(sorted((self.project / folder).rglob('*')))
        for path in candidates:
            if path.is_file():
                digest.update(str(path.relative_to(self.project)).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def execute(self, prompts, duration):
        checkpoint = self.project / 'build' / 'host_animation.json'
        identity = hashlib.sha256('\n'.join(prompts).encode()).hexdigest()
        pending = None
        try:
            saved = json.loads(checkpoint.read_text(encoding='utf-8'))
            matches = saved.get('identity') == identity and saved.get('fingerprint') == self.fingerprint()
            completed = int(saved.get('completed', 0)) if matches else 0
            pending = saved.get('pending') if matches else None
        except (OSError, ValueError, TypeError):
            completed = 0
        completed = max(0, min(completed, len(prompts)))
        def save(completed, pending=None):
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint.with_suffix('.tmp')
            temporary.write_text(json.dumps({'identity': identity, 'completed': completed,
                                             'pending': pending, 'fingerprint': self.fingerprint()}), encoding='utf-8')
            temporary.replace(checkpoint)
        for index, prompt in enumerate(prompts):
            if index < completed:
                continue
            self.check_cancel()
            if pending != index:
                self.ask(prompt + '\n\nAPP-MANAGED RENDERING OVERRIDE:\n'
                         'Keep the agent sandbox enabled. The desktop app runs Chrome, render.mjs, previews, '
                         'FFmpeg mixing and final export after your response. Do not launch browsers or render '
                         'commands, do not weaken sandbox permissions, and do not treat app-managed rendering '
                         'as a blocker. Build/fix only the scene files for this pass and prepare the requested '
                         'sound plan. Reuse existing bible, alignment, shot plan and completed scene modules; '
                         'do not recreate the project or overwrite completed work. Contact sheets will be '
                         'provided next by the app for your visual inspection. End with SCENES_READY.')
                save(index, index)
            # Three repair rounds, then a separate verification of the last repair.
            for attempt in range(4):
                try:
                    sheets = self.contact_sheets(index, len(prompts), duration)
                except RuntimeError as exc:
                    if attempt == 3:
                        raise
                    self.ask(f'The app renderer reported this failure for {self.project}:\n{exc}\n'
                             'Fix the project scene code or assets. Do not edit the installed renderer, '
                             'launch Chrome, or change sandbox permissions. The app will render again.')
                    save(index, index)
                    continue
                before_review = self.fingerprint()
                instructions = ('Fix scene code if needed; finish with QC_FIXED so the app renders again. '
                                if attempt < 3 else
                                'FINAL VERIFICATION: do not edit files in this check. If problems remain, '
                                'describe them and finish with QC_PENDING. ')
                response = self.ask(
                    f'Visual QC for project {self.project}, pass {index + 1}/{len(prompts)}. '
                    'The app rendered these real contact sheets outside your sandbox. Open and inspect '
                    'EVERY listed image with your image-reading tool:\n' + '\n'.join(map(str, sheets)) +
                    '\nCheck missing scenes, composition, legibility and style consistency. Do not run a '
                    'browser, renderer or mixer. ' + instructions +
                    'If every image was inspected and all checks pass, finish on a line '
                    'containing only QC_OK. If image inspection is unavailable, report the limitation and '
                    'do not claim QC_OK. Do not use mock-canvas tests as visual approval.')
                changed = before_review != self.fingerprint()
                save(index, index)
                if re.search(r'^QC_OK\s*$', response.strip(), re.M) and not changed:
                    break
                if not re.search(r'^QC_FIXED\s*$', response.strip(), re.M) and not changed:
                    raise RuntimeError('Visual inspection was not approved; saved at visual QC. '
                                       'Resume to check the saved scenes without rebuilding this pass.\n' + response[-1600:])
            else:
                raise RuntimeError('Visual QC still needs approval after the final verification. '
                                   'Saved at visual QC; resume with the existing scenes.')
            save(index + 1)
            pending = None
        return self.export(duration)

    def export(self, duration):
        """Only export frames from the installed renderer, never an agent's substitute MP4."""
        self.invoke(['node', 'render.mjs', '--project', str(self.project)], render=True)
        output = self.project / 'out' / 'final.mp4'
        self.invoke([str(self.python), 'audio/mix.py', '--project', str(self.project), '--out', str(output)])
        if not output.is_file() or not output.stat().st_size:
            raise RuntimeError('The app mixer did not produce the final MP4.')
        info = json.loads(self.invoke(['ffprobe', '-v', 'error', '-show_entries',
                                     'stream=codec_type:format=duration', '-of', 'json', str(output)]))
        streams = {s['codec_type'] for s in info.get('streams', [])}
        if not {'video', 'audio'} <= streams or abs(float(info['format']['duration']) - duration) > 3:
            raise RuntimeError('The final MP4 failed audio/video or duration validation.')
        return str(output)

    def export_local(self, duration):
        """Local text models cannot perform image QC; validate scenes with the real renderer."""
        try:
            story = json.loads((self.project / 'story' / 'shots.json').read_text(encoding='utf-8'))
            shots = story['shots']
            if not shots or any(str(s.get('scene', '')).strip().upper() in
                                ('', 'TODO', 'TBD', 'PLACEHOLDER') for s in shots):
                raise ValueError('The shot plan still has unfinished scene descriptions.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f'Ollama did not finish the animation: {exc} '
                               'Saved project files are preserved. No substitute video was accepted.') from exc
        self.invoke(['node', 'render.mjs', '--project', str(self.project), '--sheet', '--scale', '0.5'], render=True)
        return self.export(duration)
