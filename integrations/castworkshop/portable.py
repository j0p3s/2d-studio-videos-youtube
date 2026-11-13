"""Build and launch a self-contained Windows CastWorkshop folder without changing its source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
COPIED_FILES = 0


def disposable(path):
    # This upstream cache has built-in defaults and is regenerated on settings
    # changes. Some installations give it an unreadable Windows ACL.
    return path.name == '__pycache__' or (
        path.name == '.inline_tag_settings_cache.json'
        and tuple(path.parts[-4:-1]) == ('tts_audio_suite', 'utils', 'audio')
    )


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def copy_verified(source, target):
    """Never delete source data; keep an interrupted copy separate from a final file."""
    global COPIED_FILES
    before = source.stat()
    expected = digest(source)
    if target.exists() and target.stat().st_size == before.st_size and digest(target) == expected:
        return
    if target.exists():
        raise RuntimeError(f'Destination differs; preserved both copies: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.copying')
    shutil.copy2(source, temporary)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f'Source changed during copy: {source.name}')
    if digest(temporary) != expected:
        raise RuntimeError(f'Copy verification failed: {source.name}')
    temporary.replace(target)
    COPIED_FILES += 1
    if COPIED_FILES % 200 == 0 or before.st_size >= 1024**3:
        print(f'Copied and verified {COPIED_FILES} files this run; latest: {source.name}', flush=True)


def additional_bytes(source, target, *, ignored=()):
    """Space for remaining copies, including files already copied by hand."""
    if source.is_symlink() or source.is_junction():
        raise RuntimeError(f'Source contains a link: {source}')
    total = 0
    for child in source.iterdir():
        if child.name in ignored or disposable(child):
            continue
        destination = target / child.name
        if child.is_symlink() or child.is_junction():
            raise RuntimeError(f'Source contains a link: {child}')
        if child.is_dir():
            total += additional_bytes(child, destination)
        elif child.is_file() and not destination.is_file():
            total += child.stat().st_size
    return total


def active_processes(source):
    env = dict(os.environ, CAST_SOURCE=str(source), CAST_SKIP=f'{os.getpid()},{os.getppid()}')
    code = ("Get-CimInstance Win32_Process | Where-Object { "
            "$_.Name -match '^(python|pythonw|pip).*\\.exe$' -and $_.CommandLine -and "
            "([string]$_.ProcessId) -notin ($env:CAST_SKIP -split ',') -and "
            "$_.CommandLine.IndexOf($env:CAST_SOURCE,[StringComparison]::OrdinalIgnoreCase) -ge 0 "
            "} | Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', code], env=env,
                            capture_output=True, text=True, check=True, creationflags=NO_WINDOW)
    return json.loads(result.stdout) if result.stdout.strip() else []


def inventory(source):
    source = source.resolve()
    for name in ('ComfyUI', 'CastWorkshop'):
        if not (source / name / '.venv/pyvenv.cfg').is_file():
            raise RuntimeError(f'Missing source environment: {name}')
    partials = list((source / 'ComfyUI/models').rglob('*.part*'))
    partials += list((source / 'CastWorkshop/models').rglob('*.part*'))
    print(f'Source: {source}\nPortable destination: {ROOT}')
    print(f'Incomplete download files: {len(partials)}')
    for path in partials[:8]:
        print('  ' + str(path.relative_to(source)))
    running = active_processes(source)
    print(f'Active source Python/install processes: {running or "none"}')
    torch = source / 'ComfyUI/.venv/Lib/site-packages/torch/__init__.py'
    print('ComfyUI PyTorch installed: ' + ('yes' if torch.exists() else 'no'))
    return partials, running, torch.exists()


def verify_assets(source):
    manifest = json.loads((source / 'CastWorkshop/config/setup_dependencies.json').read_text(encoding='utf-8'))
    for asset in manifest['assets']:
        base = source / ('CastWorkshop' if asset.get('storage') == 'project' else 'ComfyUI/models')
        path = base / asset['destination']
        path.resolve().relative_to(base.resolve())
        if not path.is_file() or path.stat().st_size != asset['size']:
            raise RuntimeError(f'Model missing or incomplete: {asset["name"]}')
        print(f'Checking downloaded model: {asset["name"]}', flush=True)
        if digest(path) != asset['sha256']:
            raise RuntimeError(f'Download checksum mismatch: {asset["name"]}')


def copy_tree(source, target, *, ignored=()):
    if source.is_symlink() or source.is_junction():
        raise RuntimeError(f'Source directory is a link; inspect it before packaging: {source}')
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name in ignored or disposable(child):
            continue
        if child.is_symlink() or child.is_junction():
            raise RuntimeError(f'Source contains a link; inspect it before packaging: {child}')
        if child.is_dir():
            copy_tree(child, target / child.name)
        elif child.is_file():
            copy_verified(child, target / child.name)


def junction(link, target):
    # Only replace junctions owned by this package. Never remove a real directory.
    link.relative_to(ROOT / 'apps')
    target.resolve().relative_to(ROOT / 'models')
    if link.is_junction():
        if link.resolve() == target.resolve():
            return
        link.rmdir()
    if link.exists():
        raise RuntimeError(f'Refusing to replace a real directory: {link}')
    target.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CAST_LINK=str(link), CAST_TARGET=str(target))
    subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                    'New-Item -ItemType Junction -Path $env:CAST_LINK -Target $env:CAST_TARGET | Out-Null'],
                   env=env, check=True, creationflags=NO_WINDOW)


def python_path(name):
    return ROOT / 'runtime' / ('python-' + name) / 'python.exe'


def environment():
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'):
        env.pop(key, None)
    for key, folder in {'HF_HOME': 'cache/huggingface', 'TORCH_HOME': 'cache/torch',
                        'XDG_CACHE_HOME': 'cache', 'PIP_CACHE_DIR': 'cache/pip',
                        'TEMP': 'tmp', 'TMP': 'tmp'}.items():
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
        env[key] = str(ROOT / folder)
    env['PATH'] = os.pathsep.join([str(ROOT / 'bin'), str(python_path('comfy').parent), env.get('PATH', '')])
    env.update(COMFYUI_PATH=str(ROOT / 'apps/ComfyUI'),
               COMFY_MODELS_DIR=str(ROOT / 'models/comfyui'),
               COMFY_PYTHON=str(python_path('comfy')),
               IDENTITY_SEGMENTATION_MODEL=str(ROOT / 'models/castworkshop/u2net_human_seg.onnx'),
               FFMPEG_PATH=str(ROOT / 'bin/ffmpeg.exe'), FFPROBE_PATH=str(ROOT / 'bin/ffprobe.exe'))
    return env


def package(source):
    partials, running, torch_ready = inventory(source)
    if partials or running or not torch_ready:
        raise RuntimeError('Finish downloads and dependency installation, then close source processes before importing.')
    verify_assets(source)
    # A resumed/manual copy must not require space for another complete model set.
    total = 0
    for app, name in (('ComfyUI', 'comfy'), ('CastWorkshop', 'cast')):
        app_source = source / app
        cfg = dict(line.split(' = ', 1) for line in (app_source / '.venv/pyvenv.cfg').read_text().splitlines()
                   if ' = ' in line)
        total += additional_bytes(Path(cfg['home']), python_path(name).parent,
                                  ignored=('Scripts', 'Doc', 'include', 'libs', 'Lib'))
        total += additional_bytes(Path(cfg['home']) / 'Lib', python_path(name).parent / 'Lib', ignored=('site-packages',))
        total += additional_bytes(app_source / '.venv/Lib/site-packages', python_path(name).parent / 'Lib/site-packages')
        total += additional_bytes(app_source, ROOT / 'apps' / app, ignored=('.git', '.venv', 'models'))
        total += additional_bytes(app_source / 'models', ROOT / 'models' / ('comfyui' if name == 'comfy' else 'castworkshop'))
    print(f'Remaining copy space estimate: {total / 1024**3:.2f} GiB plus 2 GiB reserve.', flush=True)
    if shutil.disk_usage(ROOT).free < total + 2 * 1024**3:
        raise RuntimeError('Not enough free space for the remaining portable copy plus 2 GB reserve.')
    for app, name in (('ComfyUI', 'comfy'), ('CastWorkshop', 'cast')):
        app_source = source / app
        cfg = dict(line.split(' = ', 1) for line in (app_source / '.venv/pyvenv.cfg').read_text().splitlines()
                   if ' = ' in line)
        base = Path(cfg['home'])
        runtime = python_path(name).parent
        if not (base / 'python.exe').is_file():
            raise RuntimeError(f'Python base missing: {base}')
        print(f'Copying {app} and isolated Python runtime...', flush=True)
        # Avoid copying machine-wide packages into either app's isolated runtime.
        for item in base.iterdir():
            if item.name in ('Scripts', 'Doc', 'include', 'libs', '__pycache__'):
                continue
            if item.name == 'Lib':
                copy_tree(item, runtime / 'Lib', ignored=('site-packages',))
            elif item.is_dir():
                copy_tree(item, runtime / item.name)
            elif item.is_file():
                copy_verified(item, runtime / item.name)
        copy_tree(app_source / '.venv/Lib/site-packages', runtime / 'Lib/site-packages')
        copy_tree(app_source, ROOT / 'apps' / app, ignored=('.git', '.venv', 'models'))
        print(f'Copying and SHA256-verifying {app} models...', flush=True)
        copy_tree(app_source / 'models', ROOT / 'models' / ('comfyui' if name == 'comfy' else 'castworkshop'))
        junction(ROOT / 'apps' / app / 'models', ROOT / 'models' / ('comfyui' if name == 'comfy' else 'castworkshop'))
    for tool in ('ffmpeg', 'ffprobe'):
        executable = shutil.which(tool)
        if not executable:
            raise RuntimeError(f'{tool} not found; install it before packaging.')
        original = Path(executable).resolve()
        copy_verified(original, ROOT / 'bin' / (tool + '.exe'))
        for dll in original.parent.glob('*.dll'):
            copy_verified(dll, ROOT / 'bin' / dll.name)
    health()
    (ROOT / 'runtime/ready.json').write_text(json.dumps({'source': str(source), 'verified': True}), encoding='utf-8')
    use_in_studio()
    print('Portable copy created. Source on D: is unchanged. Validate a real test before removing it.')


def health():
    env = environment()
    for name, modules in (('comfy', 'import torch, yaml; print("ComfyUI torch:", torch.__version__); '
                           'print("GPU:", torch.cuda.is_available())'),
                          ('cast', 'import flask, requests, numpy; print("CastWorkshop imports OK")')):
        subprocess.run([str(python_path(name)), '-I', '-c', modules], env=env, check=True)
    for tool in ('ffmpeg', 'ffprobe'):
        subprocess.run([str(ROOT / 'bin' / (tool + '.exe')), '-version'], env=env,
                       stdout=subprocess.DEVNULL, check=True)
    print('Python and FFmpeg smoke checks passed. This does not certify all custom nodes or generation.')


def verify_tree(source, target, *, ignored=()):
    """Compare every retained source file; never follow external directory links."""
    if source.is_symlink() or source.is_junction():
        raise RuntimeError(f'Source contains a link: {source}')
    for child in source.iterdir():
        if child.name in ignored or disposable(child):
            continue
        destination = target / child.name
        if child.is_symlink() or child.is_junction():
            raise RuntimeError(f'Source contains a link: {child}')
        destination.resolve().relative_to(ROOT.resolve())
        if child.is_dir():
            verify_tree(child, destination)
        elif child.is_file():
            if not destination.is_file() or child.stat().st_size != destination.stat().st_size or digest(child) != digest(destination):
                raise RuntimeError(f'Portable file missing or different: {destination}')


def use_in_studio():
    path = ROOT.parents[1] / 'settings.json'
    if not path.is_file():
        return
    settings = json.loads(path.read_text(encoding='utf-8'))
    previous = settings.get('castworkshop_root')
    if not previous or Path(previous).resolve() == Path('D:/CastWorkshop-Test').resolve():
        backup = ROOT / 'source-backup/studio-settings-before-migration.json'
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        settings['castworkshop_root'] = str(ROOT)
        temporary = path.with_suffix('.migration.tmp')
        temporary.write_text(json.dumps(settings, indent=2), encoding='utf-8')
        temporary.replace(path)
        print('Studio CastWorkshop installation path updated. Restart Studio to reload it.')


def retire_source(source):
    """Explicit cleanup action: verify the portable copy before removing this exact source."""
    allowed = Path('D:/CastWorkshop-Test')
    if source.is_symlink() or source.is_junction() or source.resolve() != allowed.resolve():
        raise RuntimeError('Cleanup is restricted to the real D:\\CastWorkshop-Test directory.')
    source = source.resolve()
    if ROOT.resolve().drive.lower() == source.drive.lower():
        raise RuntimeError('Portable package must be outside D: before source cleanup.')
    if not (ROOT / 'runtime/ready.json').is_file():
        raise RuntimeError('Import has not completed. Finish option 2 before cleanup.')
    if active_processes(source) or active_processes(ROOT):
        raise RuntimeError('Close application, installer and importer processes before cleanup.')
    for app, name in (('ComfyUI', 'comfy'), ('CastWorkshop', 'cast')):
        print(f'Verifying every {app} application, dependency and model file...', flush=True)
        verify_tree(source / app, ROOT / 'apps' / app, ignored=('.git', '.venv', 'models'))
        verify_tree(source / app / '.venv/Lib/site-packages', python_path(name).parent / 'Lib/site-packages')
        verify_tree(source / app / 'models', ROOT / 'models' / ('comfyui' if name == 'comfy' else 'castworkshop'))
        junction(ROOT / 'apps' / app / 'models', ROOT / 'models' / ('comfyui' if name == 'comfy' else 'castworkshop'))
        # Retain source-control metadata separately without adding it to the runtime.
        if (source / app / '.git').exists():
            copy_tree(source / app / '.git', ROOT / 'source-backup' / app / '.git')
    archive = ROOT / 'source-backup/test-folder'
    ignored = ('ComfyUI', 'CastWorkshop', 'pip-cache', 'tmp')
    copy_tree(source, archive, ignored=ignored)
    verify_tree(source, archive, ignored=ignored)
    verify_assets(ROOT / 'apps')
    health()
    use_in_studio()
    if active_processes(source) or active_processes(ROOT):
        raise RuntimeError('An application started during verification; source was preserved.')
    # Revalidate the literal path immediately before recursive deletion. rmtree does
    # not traverse junction targets on supported Windows Python versions.
    if source != allowed.resolve() or source.is_junction() or source.is_symlink():
        raise RuntimeError('Source path changed; cleanup refused.')
    report = ROOT / 'runtime/source-cleanup.json'
    report.write_text(json.dumps({'source': str(source), 'verified': True,
                                 'backup': str(archive), 'deleted': False}, indent=2), encoding='utf-8')
    shutil.rmtree(source)
    record = json.loads(report.read_text(encoding='utf-8'))
    record['deleted'] = not source.exists()
    report.write_text(json.dumps(record, indent=2), encoding='utf-8')
    print('Verified portable files and removed D:\\CastWorkshop-Test. Test outputs/settings are in source-backup.')


def launch(app):
    if not (ROOT / 'runtime/ready.json').is_file():
        raise RuntimeError('Portable import has not finished successfully. Run Import first.')
    name = 'comfy' if app == 'ComfyUI' else 'cast'
    junction(ROOT / 'apps' / app / 'models', ROOT / 'models' / ('comfyui' if name == 'comfy' else 'castworkshop'))
    command = [str(python_path(name)), '-s', 'start.py']
    if name == 'comfy':
        command = [str(python_path(name)), '-s', str(ROOT / 'test-kit/comfy_bootstrap.py'),
                   str(ROOT / 'apps/ComfyUI/main.py'), '--listen', '127.0.0.1',
                   '--lowvram', '--disable-dynamic-vram']
    return subprocess.call(command, cwd=ROOT / 'apps' / app, env=environment())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=('check', 'import', 'health', 'comfy', 'cast', 'retire-source'))
    parser.add_argument('--source', type=Path, default=Path('D:/CastWorkshop-Test'))
    args = parser.parse_args()
    action = args.action
    if action is None:
        print('1. Check D: downloads/setup\n2. Import portable package (keeps D: original)\n'
              '3. Check portable runtime\n4. Start ComfyUI\n5. Start CastWorkshop (configured Telegram services)\n'
              '6. Verify portable copy, back up test outputs/settings, then DELETE D:\\CastWorkshop-Test')
        action = {'1': 'check', '2': 'import', '3': 'health', '4': 'comfy', '5': 'cast', '6': 'retire-source'}.get(input('Choose: ').strip())
        if action is None:
            return 0
    if action == 'check':
        inventory(args.source)
    elif action == 'import':
        package(args.source.resolve())
    elif action == 'health':
        health()
    elif action == 'retire-source':
        retire_source(args.source)
    else:
        return launch('ComfyUI' if action == 'comfy' else 'CastWorkshop')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('STOPPED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
