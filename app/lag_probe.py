"""Temporary diagnostic: writes a line to studio.log whenever the Studio window stops responding.

A Tk timer beats every 16 ms on the window's own thread. A watcher thread notices when the
beat stops for STALL_S and records where the main thread is. When the beat resumes it logs
how long the stall lasted and how many window move/resize events arrived meanwhile.

Reading a line:
  * "in Tk mainloop" with few events  -> the time went to Windows/Tk drawing or dragging,
    not to a Studio callback.
  * a Studio function in the stack     -> that function is blocking the window.
Set STUDIO_LAG_PROBE=0 to turn it off. Remove this file and its call in studio_gui.py once
the lag is understood.
"""
import os
import sys
import threading
import time
import traceback

STALL_S = 0.08
MAX_LINES = 60
BEAT_MS = 16
BURST_GAP_S = 0.25      # a pause this long ends one drag/resize
SLOW_TICK_S = 0.03      # a UI tick later than this is visible as stutter
MIN_BURST_EVENTS = 5


class LagProbe:
    def __init__(self, write, main_ident, clock=time.perf_counter, frames=sys._current_frames):
        self.write, self.main_ident, self.clock, self.frames = write, main_ident, clock, frames
        self.lock = threading.Lock()
        self.last_beat = clock()
        self.events = 0
        self.geom = None
        self.stall_start = None
        self.stall_events = 0
        self.stall_where = ""
        self.lines = 0
        self.stalls = 0
        self.burst = None       # [first_time, last_time, events, ticks, slow_ticks, worst_gap]

    def beat(self):
        """Main thread: the window is alive."""
        now = self.clock()
        with self.lock:
            start, self.stall_start = self.stall_start, None
            events = self.events - self.stall_events
            where, geom = self.stall_where, self.geom
            gap = now - self.last_beat
            self.last_beat = now
            done = self._tick_burst(now, gap)
        if start is not None:
            self._log(now - start, events, where, geom)
        if done:
            self._log_burst(done)

    def _tick_burst(self, now, gap):
        """Lock held. Count this UI tick against the current drag; return the drag when it has ended."""
        b = self.burst
        if b is None:
            return None
        if now - b[1] > BURST_GAP_S:
            self.burst = None
            return b
        b[3] += 1
        b[4] += gap > SLOW_TICK_S
        b[5] = max(b[5], gap)
        return None

    def configure(self, geom):
        """Main thread: the window moved or resized."""
        now = self.clock()
        with self.lock:
            self.events += 1
            self.geom = geom
            b = self.burst
            if b is None or now - b[1] > BURST_GAP_S:
                finished, self.burst = b, [now, now, 0, 0, 0, 0.0]
                b = self.burst
            else:
                finished = None
            b[1] = now
            b[2] += 1
        if finished:
            self._log_burst(finished)

    def watch(self):
        """Watcher thread: call every ~20 ms."""
        now = self.clock()
        with self.lock:
            if self.stall_start is not None or now - self.last_beat < STALL_S:
                return
            self.stall_start = self.last_beat
            self.stall_events = self.events
        where = self._where()
        with self.lock:
            self.stall_where = where

    def _where(self):
        frame = self.frames().get(self.main_ident)
        if frame is None:
            return "unknown"
        stack = traceback.extract_stack(frame)
        tail = ["%s:%d %s" % (os.path.basename(f.filename), f.lineno, f.name) for f in reversed(stack[-4:])]
        if stack and stack[-1].name == "mainloop":
            return "in Tk mainloop (not inside a Studio callback)"
        return " <- ".join(tail)

    def _log_burst(self, b):
        first, last, events, ticks, slow, worst = b
        if events < MIN_BURST_EVENTS or self.lines >= MAX_LINES:
            return
        self.lines += 1
        span = max(last - first, 1e-6)
        self.write("LAG", "Window drag/resize: %d events in %d ms (one every %.0f ms, %.0f per second); "
                          "UI ticks %d, slower than %d ms: %d, slowest gap %d ms"
                   % (events, span * 1000, span * 1000 / events, events / span, ticks,
                      SLOW_TICK_S * 1000, slow, worst * 1000))

    def _log(self, seconds, events, where, geom):
        self.stalls += 1
        if self.lines >= MAX_LINES:
            return
        self.lines += 1
        rate = "no move events" if not events else "%d move/resize events (%.0f ms apart)" % (
            events, seconds * 1000 / events)
        self.write("LAG", "UI stalled %d ms; %s; main thread %s; window %s"
                   % (seconds * 1000, rate, where or "unknown", geom))


def start(root, write):
    """Begin watching `root` (a Tk window). Returns the probe, or None when switched off."""
    if os.environ.get("STUDIO_LAG_PROBE", "1") == "0":
        return None
    probe = LagProbe(write, threading.get_ident())
    alive = {"on": True}

    def beat():
        if alive["on"]:
            probe.beat()
            root.after(BEAT_MS, beat)

    def configure(event):
        if event.widget is root:
            probe.configure((event.x, event.y, event.width, event.height))

    def destroy(event):
        if event.widget is root:
            alive["on"] = False

    def watcher():
        while alive["on"]:
            probe.watch()
            time.sleep(0.02)

    root.bind("<Configure>", configure, add="+")
    root.bind("<Destroy>", destroy, add="+")
    threading.Thread(target=watcher, name="lag-probe", daemon=True).start()
    beat()
    try:
        scaling = root._get_window_scaling()
    except Exception:
        scaling = "?"
    write("LAG", "Lag probe on: log lines start with LAG; window scaling %s, screen %dx%d, "
                 "%d widgets. Drag the window now." % (scaling, root.winfo_screenwidth(),
                                                       root.winfo_screenheight(), _count(root)))
    return probe


def _count(widget):
    return 1 + sum(_count(c) for c in widget.winfo_children())
