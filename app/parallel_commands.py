"""Independent command output and process tracking for concurrent OpenArt requests."""
import os
import subprocess
import threading


class CommandGroup:
    def __init__(self, env, *, creationflags=0, log=lambda tag, text: None):
        self.env, self.creationflags, self.log = env, creationflags, log
        self._lock = threading.Lock()
        self._processes = set()

    def run(self, cmd, cwd, check=lambda: None):
        # Stop sets the GUI cancellation flag before acquiring this same lock.
        # A newly starting command therefore either gets tracked or is refused.
        with self._lock:
            check()
            proc = subprocess.Popen(
                cmd, cwd=str(cwd), env=self.env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", creationflags=self.creationflags)
            self._processes.add(proc)
        lines = []
        try:
            self.log("RUN", f"{subprocess.list2cmdline([str(c) for c in cmd])[:600]} (PID {proc.pid})")
            for line in proc.stdout:
                self.log("OUT", f"[PID {proc.pid}] {line.rstrip()}")
                lines.append(line.rstrip("\n"))
            code = proc.wait()
            self.log("RUN", f"exit code {code}: PID {proc.pid}")
            return code, "\n".join(lines)
        finally:
            if proc.poll() is None:
                self._kill(proc)
                proc.wait()
            proc.stdout.close()
            with self._lock:
                self._processes.discard(proc)

    def _kill(self, proc):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=self.creationflags)
        if proc.poll() is None:
            proc.kill()

    def stop(self):
        with self._lock:
            for proc in tuple(self._processes):
                if proc.poll() is None:
                    self._kill(proc)
