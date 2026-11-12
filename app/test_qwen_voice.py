import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import qwen_voice
from language_policy import migrate_speech_settings, voice_engine, QWEN_ENGINE, PIPER_ENGINE, EDGE_ENGINE

TEXT = " ".join(f"The river moves slowly under the evening light on day {i}." for i in range(30))


def install_marker(home):
    python = qwen_voice.venv_python(home)
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    folder = qwen_voice.model_dir(home)
    folder.mkdir(parents=True)
    (folder / "config.json").write_text("{}")
    (folder / ".complete").write_text("ok")


class QwenVoiceTests(unittest.TestCase):
    def test_engine_name_matches_the_policy_and_defaults_are_calm(self):
        self.assertEqual(qwen_voice.ENGINE, QWEN_ENGINE)
        self.assertEqual(qwen_voice.qwen_style("unknown"), "Calm & relaxing")
        self.assertIn("calm", qwen_voice.STYLES[qwen_voice.DEFAULT_STYLE])
        self.assertEqual(qwen_voice.speaker("Uncle_Fu · low, mellow male"), "Uncle_Fu")
        self.assertEqual(qwen_voice.speaker("en_US-joe-medium"), "Aiden")

    def test_chunks_keep_every_word_and_end_on_sentences(self):
        parts = qwen_voice.chunks(TEXT)
        self.assertEqual(" ".join(parts), TEXT)
        self.assertGreater(len(parts), 2)
        self.assertTrue(all(len(p) <= qwen_voice.CHUNK_CHARS and p.endswith(".") for p in parts))
        self.assertEqual(" ".join(qwen_voice.chunks("word " * 400)), ("word " * 400).strip())

    def test_tempo_follows_the_speed_slider(self):
        self.assertEqual([qwen_voice.tempo(p) for p in (0, -10, 20, -90)], [1, 0.9, 1.2, 0.5])

    def test_qwen_choice_survives_migration_and_offline_mode(self):
        saved = migrate_speech_settings({"engine": QWEN_ENGINE, "piper_default": True})
        self.assertEqual(saved["engine"], QWEN_ENGINE)
        self.assertEqual(voice_engine({"engine": QWEN_ENGINE, "offline": True}), QWEN_ENGINE)
        self.assertEqual(voice_engine({"engine": EDGE_ENGINE, "offline": True}), PIPER_ENGINE)
        self.assertEqual(voice_engine({"engine": EDGE_ENGINE}), EDGE_ENGINE)
        self.assertEqual(voice_engine({}), EDGE_ENGINE)

    def speak(self, home, run):
        ffmpeg = []

        def fake_ffmpeg(cmd, **kwargs):
            ffmpeg.append(cmd)
            Path(cmd[-1]).write_bytes(b"mp3")
            return SimpleNamespace(returncode=0, stderr="")
        with patch("qwen_voice.subprocess.run", fake_ffmpeg):
            out = qwen_voice.speak(TEXT, home / "voiceover.mp3", rate=-10, home=home,
                                   cache=home / "voice_parts", run=run)
        return out, ffmpeg

    def test_speak_sends_the_calm_instruction_and_only_missing_passages(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            install_marker(home)
            jobs = []

            def run(cmd, on_line=None):
                job = json.loads(Path(cmd[2]).read_text(encoding="utf-8"))
                jobs.append(job)
                self.assertEqual(cmd[0], str(qwen_voice.venv_python(home)))
                for part in job["parts"]:
                    Path(part["out"]).write_bytes(b"wav")
                    on_line("QWEN done " + Path(part["out"]).name)
                return 0
            out, ffmpeg = self.speak(home, run)
            self.assertEqual(out.read_bytes(), b"mp3")
            self.assertEqual(jobs[0]["speaker"], "Aiden")
            self.assertEqual(jobs[0]["instruct"], qwen_voice.STYLES["Calm & relaxing"])
            self.assertEqual(" ".join(p["text"] for p in jobs[0]["parts"]), TEXT)
            self.assertIn("atempo=0.9", ffmpeg[0])
            self.speak(home, run)           # everything is cached: the model is not started again
            self.assertEqual(len(jobs), 1)

    def test_stopped_worker_keeps_finished_passages_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            install_marker(home)

            def run(cmd, on_line=None):
                job = json.loads(Path(cmd[2]).read_text(encoding="utf-8"))
                Path(job["parts"][0]["out"]).write_bytes(b"wav")
                on_line("QWEN error CUDA out of memory")
                return 1
            with self.assertRaisesRegex(RuntimeError, "CUDA out of memory. 1 of"):
                self.speak(home, run)
            self.assertFalse((home / "voiceover.mp3").exists())
            self.assertEqual(len(list((home / "voice_parts").glob("qwen-*.wav"))), 1)

    def test_not_installed_is_reported_before_any_work(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "not installed"):
                qwen_voice.speak(TEXT, Path(temp) / "v.mp3", home=temp, cache=Path(temp) / "c", run=None)


if __name__ == "__main__":
    unittest.main()
