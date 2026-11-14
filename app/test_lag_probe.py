import unittest

from lag_probe import LagProbe, STALL_S


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class LagProbeTests(unittest.TestCase):
    def make(self):
        self.clock, self.lines = FakeClock(), []
        return LagProbe(lambda kind, text: self.lines.append((kind, text)), 1, self.clock, lambda: {})

    def test_short_gaps_are_not_logged(self):
        p = self.make()
        for _ in range(5):
            self.clock.now += STALL_S / 2
            p.watch()
            p.beat()
        self.assertEqual(self.lines, [])

    def test_a_long_gap_is_logged_once_with_its_length_and_move_events(self):
        p = self.make()
        self.clock.now += STALL_S + 0.01
        p.watch()
        p.watch()                       # still the same stall
        p.configure((10, 20, 800, 600))
        p.configure((12, 20, 800, 600))
        self.clock.now += 0.2
        p.beat()
        self.assertEqual(len(self.lines), 1)
        kind, text = self.lines[0]
        self.assertEqual(kind, "LAG")
        self.assertIn("stalled 290 ms", text)
        self.assertIn("2 move/resize events", text)
        self.assertIn("(12, 20, 800, 600)", text)

    def test_stall_without_events_is_labelled(self):
        p = self.make()
        self.clock.now += 0.5
        p.watch()
        p.beat()
        self.assertIn("no move events", self.lines[0][1])

    def test_log_is_capped(self):
        p = self.make()
        for _ in range(200):
            self.clock.now += 0.5
            p.watch()
            p.beat()
        self.assertEqual(len(self.lines), 60)
        self.assertEqual(p.stalls, 200)

    def test_a_drag_is_summarised_with_event_rate_and_slow_ticks(self):
        p = self.make()
        for i in range(10):
            self.clock.now += 0.05
            p.configure((i, 0, 800, 600))
            p.beat()                       # 50 ms between ticks: slower than 30 ms
        self.clock.now += 1.0
        p.beat()                           # the pause ends the drag
        drags = [t for k, t in self.lines if t.startswith("Window drag")]
        self.assertEqual(len(drags), 1)
        self.assertRegex(drags[0], r"10 events in 4[45]\d ms")
        self.assertIn("slower than 30 ms: 10", drags[0])

    def test_tiny_moves_are_not_reported(self):
        p = self.make()
        for _ in range(3):
            self.clock.now += 0.01
            p.configure((0, 0, 1, 1))
            p.beat()
        self.clock.now += 1.0
        p.beat()
        self.assertEqual([t for k, t in self.lines if t.startswith("Window drag")], [])


if __name__ == "__main__":
    unittest.main()
