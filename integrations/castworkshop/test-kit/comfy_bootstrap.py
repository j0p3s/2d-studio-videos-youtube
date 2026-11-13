"""Run ComfyUI with non-mapped PyTorch safetensors reads on this Windows test stack."""
from pathlib import Path
import os
import runpy
import sys


def install_pread():
    import safetensors
    original = safetensors.safe_open

    def safe_open(*args, **kwargs):
        framework = kwargs.get('framework', args[1] if len(args) > 1 else None)
        if framework in ('pt', 'pytorch'):
            kwargs['backend'] = 'pread'
        return original(*args, **kwargs)

    safetensors.safe_open = safe_open
    # Do not import torch here: ComfyUI must configure its CUDA allocator first.
    # Future safetensors.torch imports capture the patched package-level reader.
    torch_module = sys.modules.get('safetensors.torch')
    if torch_module is not None:
        torch_module.safe_open = safe_open


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
