import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import piper_voice
import ollama_provider as ollama
from ai_providers import OLLAMA, PROVIDERS, run_agent


class FakeOllama(BaseHTTPRequestHandler):
    models = ["tiny:latest", "big:7b", "thinker"]
    seen = []
    thinker_calls, thinker_answers_on = 0, 2

    def log_message(self, *args):
        pass

    def _send(self, lines, status=200):
        body = "".join(json.dumps(line) + "\n" for line in lines).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._send([{"version": "test"}])
        elif self.path == "/api/tags":
            self._send([{"models": [{"name": name} for name in self.models]}])

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, payload))
        if self.path == "/api/chat":
            if payload["model"] == "thinker":
                FakeOllama.thinker_calls += 1
                answer = [{"message": {"content": "Done"}}] if FakeOllama.thinker_calls == FakeOllama.thinker_answers_on else []
                self._send([{"message": {"thinking": "let me plan"}}] + answer + [{"done": True, "done_reason": "stop"}])
            elif payload["model"] == "big:7b":
                self._send([{"error": "out of memory"}], 500)
            else:
                self._send([{"message": {"content": "<think>plan</think>Hello "}},
                            {"message": {"content": "there"}}, {"done": True}])
        elif self.path == "/api/create":
            self.models.append(payload["model"])
            self._send([{"status": "success"}])
        elif self.path == "/api/pull":
            self._send([{"status": "pulling", "total": 10, "completed": 5}, {"status": "success"}])


class OllamaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.env = {"OLLAMA_HOST": f"127.0.0.1:{cls.server.server_port}"}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeOllama.models[:] = ["tiny:latest", "big:7b", "thinker"]
        FakeOllama.thinker_calls, FakeOllama.thinker_answers_on = 0, 2
        FakeOllama.seen.clear()

    def test_text_streams_pieces_and_drops_thinking(self):
        pieces = []
        answer = run_agent(OLLAMA, "an idea please", None, cwd=".", env=self.env, model="tiny",
                           on_event=lambda kind, value: pieces.append((kind, value)))
        self.assertEqual(answer, "Hello there")
        self.assertEqual(pieces[-1], ("text", "there"))
        path, payload = FakeOllama.seen[-1]
        self.assertEqual((path, payload["model"]), ("/api/chat", "tiny"))
        self.assertIn("an idea please", payload["messages"][0]["content"])
        self.assertEqual(payload["options"]["num_ctx"], ollama.TEXT_CONTEXT)
        self.assertIn(OLLAMA, PROVIDERS)

    def test_missing_model_and_server_errors_are_explained(self):
        with self.assertRaisesRegex(RuntimeError, "not downloaded"):
            ollama.text("hi", model="absent:1b", env=self.env)
        with self.assertRaisesRegex(RuntimeError, "not downloaded"):
            ollama.pick_model("", self.env)          # the default model is not in the fake server
        self.assertEqual(ollama.pick_model("", dict(self.env, OLLAMA_MODEL="big:7b")), "big:7b")
        with self.assertRaisesRegex(RuntimeError, "out of memory"):
            ollama.text("hi", model="big:7b", env=self.env)

    def test_empty_answer_from_a_reasoning_model_is_asked_again(self):
        self.assertEqual(ollama.text("hi", model="thinker", env=self.env), "Done")
        self.assertEqual(FakeOllama.thinker_calls, 2)
        FakeOllama.thinker_calls, FakeOllama.thinker_answers_on = 0, 99
        with self.assertRaisesRegex(RuntimeError, "no text in 3 tries: it wrote 11 characters of reasoning"):
            ollama.text("hi", model="thinker", env=self.env)

    def test_agent_model_is_created_once_with_a_large_context(self):
        name = ollama.agent_model("big:7b", self.env)
        self.assertEqual(name, "big-7b-studio64k")
        self.assertEqual(ollama.agent_model("big:7b", self.env), name)
        created = [payload for path, payload in FakeOllama.seen if path == "/api/create"]
        self.assertEqual(created, [{"model": name, "from": "big:7b", "stream": False,
                                    "parameters": {"num_ctx": ollama.AGENT_CONTEXT}}])

    def test_claude_env_points_only_at_the_local_server(self):
        env = ollama.claude_env(dict(self.env, ANTHROPIC_API_KEY="real-key", PATH="p"), "big-7b-studio64k")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://" + self.env["OLLAMA_HOST"])
        self.assertEqual(env["ANTHROPIC_API_KEY"], "")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "big-7b-studio64k")
        self.assertEqual(env["PATH"], "p")

    def test_pull_reports_progress(self):
        seen = []
        ollama.pull("tiny", self.env, lambda fraction, status: seen.append((fraction, status)))
        self.assertEqual(seen, [(0.5, "pulling"), (None, "success")])

    def test_stopped_server_is_reported_as_not_running(self):
        self.assertFalse(ollama.is_running({"OLLAMA_HOST": "127.0.0.1:9"}))
        self.assertEqual(ollama.base_url({"OLLAMA_HOST": "0.0.0.0:11434"}), "http://127.0.0.1:11434")


class PiperVoiceTests(unittest.TestCase):
    def test_speed_maps_to_the_piper_length_scale(self):
        self.assertEqual([piper_voice.length_scale(p) for p in (-100, -20, 0, 25, 100)], [2.0, 1.25, 1.0, 0.8, 0.5])

    def test_unknown_voice_falls_back_and_missing_model_is_not_installed(self):
        self.assertEqual(piper_voice.piper_voice("en-US-AndrewMultilingualNeural"), piper_voice.DEFAULT_VOICE)
        self.assertEqual(piper_voice.piper_voice("en_GB-alan-medium"), "en_GB-alan-medium")
        self.assertFalse(piper_voice.installed(piper_voice.DEFAULT_VOICE, "no-such-folder"))


if __name__ == "__main__":
    unittest.main()
