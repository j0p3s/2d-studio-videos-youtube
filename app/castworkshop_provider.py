"""Local CastWorkshop workflow adapter; no Telegram, VPS or remote generation API."""
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urlsplit
import uuid

CASTWORKSHOP = 'CastWorkshop (local)'
DEFAULT_URL = 'http://127.0.0.1:8190'
CLIP_SECONDS = 8
WORKFLOWS = ('k2_txt2img_api.json', 'presets/minimax_h3_ref2v_widescreen.json',
             'presets/minimax_h3_ref2v_vertical.json')


def default_root(studio):
    portable = Path(studio) / 'integrations/castworkshop'
    return str(portable if (portable / 'apps/ComfyUI/main.py').is_file() else Path('D:/CastWorkshop-Test'))


def locations(root):
    root = Path(root).expanduser().resolve()
    packaged = (root / 'apps/ComfyUI/main.py').is_file()
    comfy, cast = root / ('apps/ComfyUI' if packaged else 'ComfyUI'), root / ('apps/CastWorkshop' if packaged else 'CastWorkshop')
    python = root / 'runtime/python-comfy/python.exe' if packaged else comfy / '.venv/Scripts/python.exe'
    return root, comfy, cast, python


def local_url(value):
    parts = urlsplit(value)
    try:
        local = parts.hostname == 'localhost' or ipaddress.ip_address(parts.hostname).is_loopback
    except (ValueError, TypeError):
        local = False
    if parts.scheme != 'http' or not local or parts.username or parts.password or parts.path not in ('', '/') or parts.query or parts.fragment:
        raise ValueError('CastWorkshop requires a local HTTP ComfyUI address, such as ' + DEFAULT_URL)
    _ = parts.port
    return value.rstrip('/')


def readiness(root):
    root, comfy, cast, python = locations(root)
    problems = []
    for path in (comfy / 'main.py', python, cast / 'config/setup_dependencies.json',
                 *(cast / 'worker/workflows' / f for f in WORKFLOWS)):
        if not path.is_file():
            problems.append('Missing: ' + str(path))
    manifest_path = cast / 'config/setup_dependencies.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for asset in manifest['assets']:
            # Narrated visual clips do not call MOSS or identity-background removal.
            if asset.get('storage') == 'project' or asset['destination'].startswith('TTS/'):
                continue
            path = (comfy / 'models' / asset['destination']).resolve()
            path.relative_to((comfy / 'models').resolve())
            tolerance = min(1024 * 1024, int(asset['size'] * .001))
            if not path.is_file() or abs(path.stat().st_size - asset['size']) > tolerance:
                problems.append('Model incomplete: ' + asset['name'])
    return problems


def workflow(cast, relative):
    return json.loads((cast / 'worker/workflows' / relative).read_text(encoding='utf-8'))


def image_workflow(cast, prompt, aspect, prefix):
    result = workflow(cast, WORKFLOWS[0])
    result['30:19']['inputs']['value'] = prompt
    result['49']['inputs']['aspect_ratio'] = '9:16 (Portrait Widescreen)' if aspect == '9:16' else '16:9 (Widescreen)'
    result['52']['inputs']['value'] = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
    result['57']['inputs']['filename_prefix'] = prefix
    return result, '57'


def video_workflow(cast, prompt, reference, aspect, prefix):
    result = workflow(cast, WORKFLOWS[2] if aspect == '9:16' else WORKFLOWS[1])
    result['137']['inputs']['image'] = reference
    # Audio references are optional in the upstream H3 schema. Studio owns narration.
    result.pop('141', None)
    result['136']['inputs'].pop('ref_audios.ref_audio_0', None)
    result['132']['inputs']['value'] = CLIP_SECONDS
    result['138']['inputs']['value'] = (
        'For the target video, at 0.00 seconds, <Picture 1> is fully referenced. '
        'Preserve its subject, clothing, setting and lighting. ' + prompt +
        ' This is a visual illustration under an external narrator: no speaking or lip-sync, '
        'no new characters, text, logos or watermarks. Use restrained anticipation, action and settling.')
    result['129']['inputs']['noise_seed'] = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
    result['92']['inputs']['filename_prefix'] = prefix
    return result, '92'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temp.replace(path)


class Session:
    def __init__(self, root, url, cache, *, env, check, log):
        self.root, self.comfy, self.cast, self.python = locations(root)
        self.url = local_url(url)
        self.cache = Path(cache)
        self.env, self.check, self.log = dict(env), check, log
        self.process = None
        self.lock = None

    def api(self, path, data=None):
        self.check()
        parts = urlsplit(self.url)
        connection = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=5)
        try:
            connection.request('POST' if data is not None else 'GET', path,
                               body=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            body = response.read()
            if response.status >= 400:
                raise RuntimeError(f'ComfyUI HTTP {response.status}: ' + body.decode('utf-8', 'replace')[:2000])
            return json.loads(body)
        finally:
            connection.close()

    def __enter__(self):
        problems = readiness(self.root)
        if problems:
            raise RuntimeError('CastWorkshop is not ready. Use Setup → Finish CastWorkshop setup.\n' + '\n'.join(problems[:12]))
        self.cache.mkdir(parents=True, exist_ok=True)
        # Use the upstream shared GPU lock, without starting its worker or Telegram.
        import importlib.util
        spec = importlib.util.spec_from_file_location('_cast_runtime', self.cast / 'scripts/runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.lock = module.InstanceLock(module.resource_identity(self.url))
        if not self.lock.acquire():
            raise RuntimeError('CastWorkshop/ComfyUI is already owned by another local job.')
        try:
            self.start()
        except BaseException:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=30)
            self.lock.close()
            raise
        return self

    def start(self):
        self.cache.mkdir(parents=True, exist_ok=True)
        try:
            stats = self.api('/system_stats')
        except (OSError, ValueError, http.client.HTTPException):
            stats = None
        if stats:
            argv = ' '.join(stats.get('system', {}).get('argv', []))
            # Do not silently submit to an unrelated installation using this port.
            if str(self.comfy).lower().replace('\\', '/') not in argv.lower().replace('\\', '/'):
                raise RuntimeError('ComfyUI port is already in use by an unverified installation. '
                                   'Use a free port in Setup or stop that server yourself.')
            self.log('Using the configured local ComfyUI server.')
            return
        self.log('Starting local ComfyUI with --lowvram; server log: ' + str(self.cache / 'server.log'))
        env = dict(self.env)
        env.pop('PYTHONHOME', None)
        env.pop('PYTHONPATH', None)
        env['PYTHONUTF8'] = '1'
        port = str(urlsplit(self.url).port or 80)
        with (self.cache / 'server.log').open('a', encoding='utf-8') as log:
            self.process = subprocess.Popen([str(self.python), str(self.comfy / 'main.py'),
                '--listen', urlsplit(self.url).hostname, '--port', port, '--lowvram', '--disable-auto-launch',
                '--offline'], cwd=self.comfy, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            self.check()
            if self.process.poll() is not None:
                raise RuntimeError('ComfyUI startup failed. Read ' + str(self.cache / 'server.log'))
            try:
                if self.api('/system_stats'):
                    return
            except (OSError, ValueError, http.client.HTTPException):
                pass
            time.sleep(.2)
        raise RuntimeError('ComfyUI startup timed out. Read ' + str(self.cache / 'server.log'))

    def __exit__(self, *args):
        # Keep accepted jobs/server alive after Stop; saved IDs are polled on resume.
        if self.lock:
            self.lock.close()

    def generate(self, graph, save_id, destination, kind):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        state_path = destination.parent / 'jobs' / (destination.name + '.json')
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        key = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()
        if state and state.get('key') != key:
            raise RuntimeError('Saved CastWorkshop job uses different inputs; use a new project to preserve it.')
        output = destination / ('result.png' if kind == 'image' else 'result.mp4')
        if output.is_file() and output.stat().st_size:
            return output
        if state.get('submitting'):
            raise RuntimeError('An earlier ComfyUI submission is unresolved. Inspect queue/history before retrying; '
                               'no duplicate job was submitted. State: ' + str(state_path))
        if not state.get('prompt_id'):
            nodes = self.api('/object_info')
            missing = sorted({node['class_type'] for node in graph.values()} - nodes.keys())
            if missing:
                raise RuntimeError('Missing ComfyUI nodes: ' + ', '.join(missing) + '. Finish setup and restart ComfyUI.')
            queue = self.api('/queue')
            if queue.get('queue_running') or queue.get('queue_pending'):
                raise RuntimeError('ComfyUI has a running or queued job. Wait for it before continuing Auto.')
            state = {'key': key, 'submitting': True}
            save(state_path, state)
            try:
                result = self.api('/prompt', {'prompt': graph, 'client_id': str(uuid.uuid4())})
            except RuntimeError as exc:
                if str(exc).startswith(('ComfyUI HTTP 400:', 'ComfyUI HTTP 422:')):
                    save(state_path, {'key': key, 'rejected': str(exc)})
                raise
            if result.get('node_errors') or not result.get('prompt_id'):
                save(state_path, {'key': key, 'rejected': result})
                raise RuntimeError('ComfyUI rejected the workflow: ' + str(result)[:2000])
            state = {'key': key, 'prompt_id': result['prompt_id']}
            save(state_path, state)
        prompt_id = state['prompt_id']
        self.log(f'CastWorkshop {kind} job: {prompt_id}')
        deadline, update = time.monotonic() + 7200, 0
        while time.monotonic() < deadline:
            self.check()
            try:
                history = self.api('/history/' + prompt_id)
            except (OSError, ValueError, http.client.HTTPException):
                time.sleep(.2)
                continue
            if prompt_id in history:
                entry = history[prompt_id]
                save(state_path.with_suffix('.history.json'), entry)
                if entry.get('status', {}).get('status_str') == 'error':
                    raise RuntimeError('CastWorkshop job failed. Details: ' + str(state_path.with_suffix('.history.json')))
                media = entry.get('outputs', {}).get(save_id, {})
                items = next((media[k] for k in ('images', 'videos', 'gifs') if media.get(k)), [])
                if not items:
                    raise RuntimeError('ComfyUI finished without expected media; preserved job history.')
                item = items[0]
                source = (self.comfy / ('input' if item.get('type') == 'input' else 'output') /
                          item.get('subfolder', '') / item['filename']).resolve()
                source.relative_to(self.comfy.resolve())
                self.check()
                # All generation is local; keep the original ComfyUI output as well.
                temporary = output.with_suffix('.copying')
                shutil.copy2(source, temporary)
                temporary.replace(output)
                self.api('/free', {'unload_models': True, 'free_memory': True})
                return output
            if time.monotonic() > update:
                self.log('Waiting for local GPU render; Stop preserves the accepted job for resume.')
                update = time.monotonic() + 30
            time.sleep(.2)
        raise RuntimeError('Local GPU job timed out; its saved ID will be polled rather than resubmitted.')

    def make_still(self, prompt, aspect, destination):
        graph, save_id = image_workflow(self.cast, prompt, aspect, 'StudioCast/reference')
        return self.generate(graph, save_id, destination, 'image')

    def make_clip(self, prompt, still, aspect, resolution, destination):
        data = Path(still).read_bytes()
        name = 'StudioCast-' + hashlib.sha256(data).hexdigest()[:20] + Path(still).suffix
        shutil.copy2(still, self.comfy / 'input' / name)
        graph, save_id = video_workflow(self.cast, prompt, name, aspect, 'StudioCast/video')
        return self.generate(graph, save_id, destination, 'video')
