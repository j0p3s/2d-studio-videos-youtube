"""Run ComfyUI with non-mapped PyTorch safetensors reads on this Windows test stack."""
from pathlib import Path
import os
import runpy
import sys


def install_pread():
    import safetensors
    import safetensors.torch
    original = safetensors.safe_open

    def safe_open(*args, **kwargs):
        framework = kwargs.get('framework', args[1] if len(args) > 1 else None)
        if framework in ('pt', 'pytorch'):
            kwargs['backend'] = 'pread'
        return original(*args, **kwargs)

    safetensors.safe_open = safe_open
    safetensors.torch.safe_open = safe_open


def main():
    script = Path(sys.argv[1]).resolve()
    if script.name != 'main.py' or not script.is_file():
        raise RuntimeError('Expected the installed ComfyUI main.py path')
    sys.argv = [str(script), *sys.argv[2:]]
    sys.path.insert(0, str(script.parent))
    os.chdir(script.parent)
    install_pread()
    print('[CastWorkshop] PyTorch safetensors backend: pread (memory mapping bypassed)', flush=True)
    runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    main()
