"""Standalone local Krea -> MOSS -> H3 test. No Telegram, Ollama or model relocation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib import error, request
import uuid

ROOT = Path(__file__).resolve().parent
CAST = ROOT / 'CastWorkshop'
COMFY = ROOT / 'ComfyUI'
PYTHON = COMFY / '.venv/Scripts/python.exe'
LOGS = ROOT / 'logs'
URL = 'http://127.0.0.1:8190'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
SERVER_PROCESS = None


def environment():
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    env.update(PYTHONUTF8='1', PYTHONUNBUFFERED='1', PYTHONFAULTHANDLER='1', PIP_CACHE_DIR=str(ROOT / 'pip-cache'),
               TEMP=str(ROOT / 'tmp'), TMP=str(ROOT / 'tmp'), COMFY_URL=URL,
               COMFYUI_PATH=str(COMFY), COMFY_MODELS_DIR=str(COMFY / 'models'), COMFY_PYTHON=str(PYTHON))
    return env


def run_logged(command, name, cwd=ROOT):
    print(f'[{name}] Running; log: {LOGS / (name + ".log")}', flush=True)
    with (LOGS / (name + '.log')).open('a', encoding='utf-8') as log:
        process = subprocess.Popen([str(v) for v in command], cwd=cwd, env=environment(),
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=FLAGS)
        try:
            while process.poll() is None:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    print(f'[{name}] Still running. Progress is in the log.', flush=True)
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            raise
    if process.returncode:
        raise RuntimeError(f'{name} failed (exit {process.returncode}). Read {LOGS / (name + ".log")}')


def source_processes(pattern):
    env = dict(os.environ, TEST_ROOT=str(ROOT), TEST_PATTERN=pattern)
    script = ("Get-CimInstance Win32_Process | Where-Object { "
              "$_.ProcessId -ne " + str(os.getpid()) + " -and $_.Name -match '^python(w)?\\.exe$' "
              "-and $_.CommandLine -and $_.CommandLine.IndexOf($env:TEST_ROOT,"
              "[StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine -match $env:TEST_PATTERN "
              "} | Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress")
    output = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', script],
                                     env=env, text=True, creationflags=FLAGS).strip()
    found = json.loads(output) if output else []
    return found if isinstance(found, list) else [found]


def wait_for_existing(pattern, label):
    deadline = time.monotonic() + 7200
    while ids := source_processes(pattern):
        if time.monotonic() > deadline:
            raise RuntimeError(f'{label} is still running; no competing writer was started.')
        print(f'Waiting for existing {label} (PID {ids}); Ctrl+C stops this launcher.', flush=True)
        time.sleep(10)


def api(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = request.Request(URL + path, data=body, headers={'Content-Type': 'application/json'})
    try:
        with request.urlopen(req, timeout=30) as reply:
            body = reply.read()
            return json.loads(body) if body.strip() else {}
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')
        raise RuntimeError(f'ComfyUI HTTP {exc.code}: {detail[:3000]}') from None


def probe():
    try:
        with request.urlopen(URL + '/system_stats', timeout=2) as reply:
            data = json.load(reply)
        # Our own running PID/argv is also checked by start_server before reuse.
        return data
    except (OSError, ValueError):
        return None


def check():
    sys.path.insert(0, str(CAST))
    from scripts.comfy_setup import load_dependencies, asset_target, model_size_matches
    missing = []
    assets = load_dependencies()['assets']
    for asset in assets:
        if not model_size_matches(asset_target(COMFY / 'models', asset), asset['size']):
            missing.append(asset['name'])
    print(f'Model assets ready: {len(assets)-len(missing)}/{len(assets)}')
    for name in missing:
        print('  Missing/incomplete: ' + name)
    torch = subprocess.run([str(PYTHON), '-c',
                            'import torch, torchvision, torchaudio; '
                            'print("Torch:",torch.__version__,"CUDA:",torch.cuda.is_available()); '
                            'assert torch.cuda.is_available(), "CUDA GPU is unavailable"'],
                           env=environment(), capture_output=True, text=True)
    print(torch.stdout.strip() or 'CUDA PyTorch is not installed/ready.')
    if torch.returncode:
        print(torch.stderr[-700:])
    print('Telegram: not used. Models: remain on D:.')
    return not missing and torch.returncode == 0


def setup():
    wait_for_existing(r'-m\s+pip\b', 'pip installation')
    ready = subprocess.run([str(PYTHON), '-c',
                            'import torch, torchvision, torchaudio; assert torch.cuda.is_available()'],
                           env=environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ready.returncode:
        run_logged([PYTHON, '-m', 'pip', 'install', 'torch', 'torchvision', 'torchaudio',
                    '--index-url', 'https://download.pytorch.org/whl/cu130', '--timeout', '60',
                    '--retries', '3', '--progress-bar', 'off'], 'torch-install')
    run_logged([PYTHON, '-c', 'import torch, torchvision, torchaudio; '
                'assert torch.cuda.is_available(), "CUDA PyTorch/driver is not ready"'], 'cuda-check')
    # Preserve the installed CUDA wheels while resolving ComfyUI dependencies.
    versions = subprocess.check_output([str(PYTHON), '-c',
               'import importlib.metadata as m; print("\\n".join(n+"=="+m.version(n) '
               'for n in ("torch","torchvision","torchaudio")))'], env=environment(), text=True)
    constraints = LOGS / 'torch-constraints.txt'
    constraints.write_text(versions, encoding='utf-8')
    run_logged([PYTHON, '-m', 'pip', 'install', '-c', constraints, '-r', COMFY / 'requirements.txt',
                '--progress-bar', 'off'], 'comfy-requirements')
    # Node archives/dependencies do not write model partials, so they can be
    # prepared while the user's original model downloader remains open.
    node_setup = (
        'import sys; sys.path.insert(0,sys.argv[1]); '
        'from scripts.comfy_setup import load_dependencies,install_groups; '
        'manifest=load_dependencies(); manifest["assets"]=[]; '
        'result=install_groups(sys.argv[2],["images","video"],python=sys.argv[3],manifest=manifest); '
        'sys.exit(1 if result["failures"] else 0)')
    run_logged([sys.executable, '-c', node_setup, CAST, COMFY, PYTHON], 'custom-nodes', cwd=CAST)
    wait_for_existing('download_models.py', 'model downloader')
    run_logged([sys.executable, CAST / 'scripts/comfy_setup.py', '--images', '--video',
                '--comfyui-path', COMFY, '--comfy-python', PYTHON, '--models-dir', COMFY / 'models'],
               'nodes-and-models', cwd=CAST)
    run_logged([PYTHON, '-m', 'pip', 'check'], 'pip-check')
    if not check():
        raise RuntimeError('Setup is still incomplete. No GPU generation was submitted.')


def start_server():
    global SERVER_PROCESS
    if probe():
        owners = source_processes(r'main.py.*--port\s+8190')
        if not owners:
            raise RuntimeError('Port 8190 belongs to another server; refusing to use or stop it.')
        print('Reusing this D: test ComfyUI server on port 8190.')
        return None
    log = (LOGS / 'comfy-server.log').open('a', encoding='utf-8')
    try:
        process = subprocess.Popen([str(PYTHON), str(ROOT / 'comfy_bootstrap.py'), str(COMFY / 'main.py'), '--listen', '127.0.0.1', '--port', '8190',
                                    '--lowvram', '--disable-dynamic-vram', '--disable-auto-launch'], cwd=COMFY, env=environment(),
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=FLAGS)
        SERVER_PROCESS = process
    finally:
        log.close()
    print('Starting test ComfyUI on port 8190 with --lowvram and dynamic VRAM disabled for this test.', flush=True)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('ComfyUI stopped during startup. Read logs/comfy-server.log.')
        if probe():
            return process
        time.sleep(2)
    process.terminate()
    raise RuntimeError('ComfyUI startup timed out; read logs/comfy-server.log.')


def save_state(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)


def stage(name, workflow, save_id, folder, recover_missing=True):
    state_path = folder / (name + '-state.json')
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get('artifact') and Path(state['artifact']).is_file():
        return Path(state['artifact'])
    if state.get('submitting'):
        raise RuntimeError(f'{name}: earlier submission outcome is unknown. Inspect ComfyUI queue/history '
                           'and the saved state before retrying; no duplicate was submitted.')
    if not state.get('prompt_id'):
        nodes = api('/object_info')
        missing = sorted({v['class_type'] for v in workflow.values()} - nodes.keys())
        if missing:
            raise RuntimeError('Workflow nodes missing: ' + ', '.join(missing))
        queue = api('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise RuntimeError('ComfyUI is busy. Refusing an overlapping test submission.')
        save_state(state_path, {'submitting': True})
        save_state(folder / (name + '-workflow.json'), workflow)
        try:
            result = api('/prompt', {'prompt': workflow, 'client_id': str(uuid.uuid4())})
        except RuntimeError as exc:
            # Validation rejection is definite; a server error may follow acceptance.
            if str(exc).startswith(('ComfyUI HTTP 400:', 'ComfyUI HTTP 422:')):
                save_state(state_path, {'rejected': str(exc)})
            raise
        if result.get('node_errors') or not result.get('prompt_id'):
            save_state(state_path, {'rejected': result})
            raise RuntimeError(f'{name}: workflow rejected: {result}')
        state = {'prompt_id': result['prompt_id']}
        save_state(state_path, state)
    prompt_id = state['prompt_id']
    print(f'{name}: job {prompt_id}. Rendering may take a long time.', flush=True)
    deadline, update, failed_reads = time.monotonic() + 7200, 0, 0
    missing_reads = 0
    while time.monotonic() < deadline:
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is not None:
            state['server_exit_code'] = SERVER_PROCESS.returncode
            save_state(state_path, state)
            raise RuntimeError(f'ComfyUI exited during {name} (code {SERVER_PROCESS.returncode}). '
                               'The job ID is preserved. Read logs/comfy-server.log before retrying.')
        try:
            history = api('/history/' + prompt_id)
            queue = api('/queue') if prompt_id not in history else {}
        except (OSError, ValueError):
            failed_reads += 1
            if failed_reads >= 6:
                raise RuntimeError(f'Lost ComfyUI while waiting for {name}. Job {prompt_id} is preserved; '
                                   'no duplicate was submitted. Read logs/comfy-server.log.')
            print(f'{name}: ComfyUI is not responding ({failed_reads}/6).', flush=True)
            time.sleep(5)
            continue
        failed_reads = 0
        if prompt_id not in history:
            queued = queue.get('queue_running', []) + queue.get('queue_pending', [])
            present = any(len(item) > 1 and item[1] == prompt_id for item in queued)
            missing_reads = 0 if present else missing_reads + 1
            if missing_reads >= 3:
                # Check history again: the job may finish between the two GETs.
                if prompt_id in api('/history/' + prompt_id):
                    continue
                if queued or not recover_missing:
                    raise RuntimeError(f'{name}: saved job {prompt_id} is missing from queue/history. '
                                       'No replacement was submitted; inspect ComfyUI before retrying.')
                backup = folder / (name + '-state-lost-' + uuid.uuid4().hex + '.json')
                shutil.copy2(state_path, backup)
                save_state(state_path, {'recovered_missing_prompt_id': prompt_id})
                print(f'{name}: saved job {prompt_id} was lost after a restart or history reset. '
                      f'Queue is idle; state backed up to {backup.name}. Submitting one replacement.', flush=True)
                return stage(name, workflow, save_id, folder, recover_missing=False)
        if prompt_id in history:
            entry = history[prompt_id]
            save_state(folder / (name + '-history.json'), entry)
            if entry.get('status', {}).get('status_str') == 'error':
                raise RuntimeError(f'{name} failed; read {folder / (name + "-history.json")}')
            output = entry.get('outputs', {}).get(save_id, {})
            files = next((output[key] for key in ('videos', 'gifs', 'images', 'audio') if output.get(key)), [])
            if not files:
                raise RuntimeError(f'{name} completed without its expected media output.')
            item = files[0]
            source = (COMFY / ('input' if item.get('type') == 'input' else 'output') /
                      item.get('subfolder', '') / item['filename']).resolve()
            source.relative_to(COMFY.resolve())
            target = folder / (name + source.suffix)
            shutil.copy2(source, target)
            state['artifact'] = str(target)
            save_state(state_path, state)
            api('/free', {'unload_models': True, 'free_memory': True})
            return target
        if time.monotonic() >= update:
            print(f'{name}: checking saved job in queue/history; see logs/comfy-server.log.', flush=True)
            update = time.monotonic() + 30
        time.sleep(5)
    raise RuntimeError(f'{name} timed out. Saved job ID {prompt_id}; it will not be resubmitted.')


def load_workflow(relative):
    return json.loads((CAST / 'worker/workflows' / relative).read_text(encoding='utf-8'))


def test():
    settings = json.loads((ROOT / 'test_settings.json').read_text(encoding='utf-8'))
    identity = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]
    folder = ROOT / 'test-output' / identity
    folder.mkdir(parents=True, exist_ok=True)
    server = start_server()
    print('Test: Krea reference image -> MOSS voice -> approximately 15-second H3 video.')
    try:
        image = load_workflow('k2_txt2img_api.json')
        image['30:19']['inputs']['value'] = settings['image_prompt']
        image['52']['inputs']['value'] = settings['seed']
        image['49']['inputs']['aspect_ratio'] = '16:9 (Widescreen)'
        image['57']['inputs']['filename_prefix'] = 'CastWorkshopTest/reference'
        image_path = stage('reference', image, '57', folder)
        voice = load_workflow('TTS_Suite_MOSS_Unload.json')
        voice['7']['inputs'].update(reference_text=settings['dialogue'],
                                    voice_instruction=settings['voice_description'], seed=settings['seed'])
        voice['11']['inputs']['filename_prefix'] = 'CastWorkshopTest/voice'
        voice_path = stage('voice', voice, '11', folder)
        video = load_workflow('presets/minimax_h3_ref2v_widescreen.json')
        for path, node, key in ((image_path, '137', 'image'), (voice_path, '141', 'audio')):
            name = f'CastWorkshopTest-{identity}-{path.name}'
            shutil.copy2(path, COMFY / 'input' / name)
            video[node]['inputs'][key] = name
        video['132']['inputs']['value'] = settings['duration']
        video['129']['inputs']['noise_seed'] = settings['seed']
        video['138']['inputs']['value'] = (
            'For the target video, at 0.00 seconds into the target video, '
            '<Picture 1> (from [Shot 1]) is fully referenced.\n\n' + settings['video_prompt'])
        video['92']['inputs']['filename_prefix'] = 'CastWorkshopTest/final'
        result = stage('final', video, '92', folder)
        ffprobe = shutil.which('ffprobe')
        if not ffprobe:
            raise RuntimeError('Video saved, but ffprobe is missing for final audio/video validation.')
        info = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_entries',
                           'stream=codec_type:format=duration', '-of', 'json', str(result)], text=True))
        kinds = {s['codec_type'] for s in info.get('streams', [])}
        if not {'audio', 'video'} <= kinds or abs(float(info['format']['duration']) - settings['duration']) > 1:
            raise RuntimeError('Final video failed audio/video/duration checks. Saved file is preserved.')
        save_state(folder / 'result.json', {'output': str(result), 'media': info})
        print(f'TEST COMPLETE: {result}', flush=True)
    finally:
        # Do not kill a server with an unresolved/ongoing render after an interruption.
        if server is not None:
            try:
                queue = api('/queue')
                if not queue.get('queue_running') and not queue.get('queue_pending'):
                    server.terminate()
                    server.wait(timeout=30)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                print('Test server left running. Inspect logs before starting another test.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Report readiness without installing or rendering')
    parser.add_argument('--setup-only', action='store_true', help='Install/resume dependencies without GPU generation')
    parser.add_argument('--skip-setup', action='store_true', help='Run test using already installed dependencies')
    args = parser.parse_args()
    LOGS.mkdir(exist_ok=True)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    # One launcher owns setup/test state. Existing model downloads are waited for separately.
    sys.path.insert(0, str(CAST))
    from scripts.runtime import InstanceLock
    os.environ['CC_LOCK_DIR'] = str(LOGS / 'locks')
    lock = InstanceLock(str(ROOT / 'test-launcher'))
    if not lock.acquire():
        raise RuntimeError('This test launcher is already running. Do not start another copy.')
    try:
        if args.check:
            return 0 if check() else 2
        if not args.skip_setup:
            setup()
        if not args.setup_only:
            if not check():
                raise RuntimeError('Dependencies/models are incomplete. Run the launcher without --skip-setup.')
            test()
    finally:
        lock.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nStopped. A submitted GPU job may still be running; its saved ID prevents duplicate submissions.')
        sys.exit(130)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
