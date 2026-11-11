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
        try:
            saved = json.loads(checkpoint.read_text(encoding='utf-8'))
            completed = int(saved.get('completed', 0)) if (saved.get('identity') == identity and
                                                          saved.get('fingerprint') == self.fingerprint()) else 0
        except (OSError, ValueError, TypeError):
            completed = 0
        completed = max(0, min(completed, len(prompts)))
        for index, prompt in enumerate(prompts):
            if index < completed:
                continue
            self.check_cancel()
            self.ask(prompt + '\n\nAPP-MANAGED RENDERING OVERRIDE:\n'
                     'Keep the agent sandbox enabled. The desktop app runs Chrome, render.mjs, previews, '
                     'FFmpeg mixing and final export after your response. Do not launch browsers or render '
                     'commands, do not weaken sandbox permissions, and do not treat app-managed rendering '
                     'as a blocker. Build/fix only the scene files for this pass and prepare the requested '
                     'sound plan. Reuse existing bible, alignment, shot plan and completed scene modules; '
                     'do not recreate the project or overwrite completed work. Contact sheets will be '
                     'provided next by the app for your visual inspection. End with SCENES_READY.')
            for attempt in range(3):
                try:
                    sheets = self.contact_sheets(index, len(prompts), duration)
                except RuntimeError as exc:
                    if attempt == 2:
                        raise
                    self.ask(f'The app renderer reported this failure for {self.project}:\n{exc}\n'
                             'Fix the project scene code or assets. Do not edit the installed renderer, '
                             'launch Chrome, or change sandbox permissions. The app will render again.')
                    continue
                response = self.ask(
                    f'Visual QC for project {self.project}, pass {index + 1}/{len(prompts)}. '
                    'The app rendered these real contact sheets outside your sandbox. Open and inspect '
                    'EVERY listed image with your image-reading tool:\n' + '\n'.join(map(str, sheets)) +
                    '\nCheck missing scenes, composition, legibility and style consistency. Do not run a '
                    'browser, renderer or mixer. Fix scene code if needed; finish with QC_FIXED so the app '
                    'renders again. If every image was inspected and all checks pass, finish on a line '
                    'containing only QC_OK. If image inspection is unavailable, report the limitation and '
                    'do not claim QC_OK. Do not use mock-canvas tests as visual approval.')
                if re.search(r'^QC_OK\s*$', response.strip(), re.M):
                    break
                if not re.search(r'^QC_FIXED\s*$', response.strip(), re.M):
                    raise RuntimeError('Visual inspection was not approved; scene files and sheets are saved.\n' + response[-1600:])
            else:
                raise RuntimeError('Visual QC still needs fixes after three checks. Resume with the saved scenes.')
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint.with_suffix('.tmp')
            temporary.write_text(json.dumps({'identity': identity, 'completed': index + 1,
                                             'fingerprint': self.fingerprint()}), encoding='utf-8')
            temporary.replace(checkpoint)
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
