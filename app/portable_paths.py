"""Studio-owned data lives beside the launchers; environment changes are child-local."""
import json
import os
import shutil
import zipfile
from pathlib import Path


def local_environment(root, base=None):
    root = Path(root).resolve()
    env = dict(os.environ if base is None else base)
    home = root / '.runtime' / 'home'
    paths = {
        'HOME': home, 'USERPROFILE': home,
        'APPDATA': home / 'AppData' / 'Roaming',
        'LOCALAPPDATA': home / 'AppData' / 'Local',
        'CLAUDE_CONFIG_DIR': root / '.claude', 'CODEX_HOME': root / '.codex',
        'GEMINI_CLI_HOME': home,
        'TEMP': root / '.runtime' / 'tmp', 'TMP': root / '.runtime' / 'tmp',
        'XDG_CACHE_HOME': root / '.cache', 'HF_HOME': root / '.cache' / 'huggingface',
        'PIP_CACHE_DIR': root / '.cache' / 'pip',
        'npm_config_cache': root / '.cache' / 'npm',
        'npm_config_prefix': root / '.tools',
        'PLAYWRIGHT_BROWSERS_PATH': root / '.cache' / 'playwright',
    }
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env['PATH'] = str(root / '.tools') + os.pathsep + env.get('PATH', '')
    return env


def migrate_legacy(root, legacy):
    """Copy missing files only, then rebase copied JSON paths. Keep source as backup."""
    root, legacy = Path(root).resolve(), Path(legacy).resolve()
    if root == legacy or not legacy.is_dir():
        return 0
    count = 0
    for name in ('settings.json', 'python.txt', 'work', 'youtube', 'growkaz-stickman-studio'):
        source = legacy / name
        files = source.rglob('*') if source.is_dir() else [source]
        for src in files:
            if not src.is_file() or src.is_symlink():
                continue
            dest = root / src.relative_to(legacy)
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            if dest.suffix == '.json' and ('work' in dest.relative_to(root).parts or dest.name == 'settings.json' or dest.name == 'config.json'):
                try:
                    data = json.loads(dest.read_text(encoding='utf-8'))
                    def rebase(value):
                        if isinstance(value, str):
                            return value.replace(str(legacy), str(root)).replace(legacy.as_posix(), root.as_posix())
                        if isinstance(value, list):
                            return [rebase(v) for v in value]
                        if isinstance(value, dict):
                            return {k: rebase(v) for k, v in value.items()}
                        return value
                    dest.write_text(json.dumps(rebase(data), indent=2), encoding='utf-8')
                except (ValueError, UnicodeError):
                    pass
            count += 1
    return count


def install_local_skills(root):
    root = Path(root).resolve()
    archive = root / 'plugin' / 'GrowKaz_Stickman.plugin'
    skills = root / '.claude' / 'skills'
    if archive.exists():
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                parts = Path(item.filename).parts
                if len(parts) < 3 or parts[0] != 'skills' or 'kit' in parts or '..' in parts:
                    continue
                dest = skills.joinpath(*parts[1:])
                if not item.is_dir() and not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(bundle.read(item))
    source = root / 'app' / 'skills' / 'scriptforge'
    if source.is_dir():
        shutil.copytree(source, skills / 'scriptforge', dirs_exist_ok=True)


if __name__ == '__main__':
    import sys
    print('Legacy files copied:', migrate_legacy(Path(__file__).resolve().parent.parent,
                                               Path.home() / '2D-Animation-Studio'))
    install_local_skills(Path(__file__).resolve().parent.parent)
