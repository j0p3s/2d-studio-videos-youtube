import unittest
from unittest.mock import patch

import model_choices
from model_choices import DEFAULT, available, check
from ollama_provider import OLLAMA
from openart_provider import OPENART


class ModelChoicesTests(unittest.TestCase):
    def test_only_listed_models_pass_the_check(self):
        names = ["gemini-3.8-flash", "gpt-oss:latest"]
        self.assertEqual(check("gemini-3.8-flash", names), ("gemini-3.8-flash", ""))
        self.assertEqual(check("gpt-oss", names), ("gpt-oss", ""))          # Ollama short form
        model, problem = check("made-up-model", names)
        self.assertIsNone(model)
        self.assertIn("not on the provider's model list", problem)

    def test_default_and_blank_save_an_empty_setting(self):
        self.assertEqual(check(DEFAULT, ["a"]), ("", ""))
        self.assertEqual(check("  ", ["a"]), ("", ""))

    def test_without_a_list_the_typed_name_is_kept_unchecked(self):
        self.assertEqual(check("anything", None), ("anything", ""))

    def test_gemini_list_keeps_text_models_that_support_generate_content(self):
        reply = {"models": [
            {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.1-flash-image", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedder", "supportedGenerationMethods": ["embedContent"]}]}
        seen = {}

        def get(url, headers):
            seen.update(url=url, headers=headers)
            return reply
        with patch("model_choices._get", get):
            names, note = available("Gemini API", {"GEMINI_API_KEY": "secret"})
        self.assertEqual((names, note), (["gemini-3.8-flash"], ""))
        self.assertNotIn("secret", seen["url"])                # the key is sent in a header only
        self.assertEqual(seen["headers"]["x-goog-api-key"], "secret")

    def test_providers_without_a_readable_list_offer_no_names(self):
        for provider, env in (("Claude", {}), ("OpenAI (Codex)", {}), ("Gemini", {})):
            names, note = available(provider, env)
            self.assertIsNone(names)
            self.assertTrue(note)
        with patch("ollama_provider.is_running", return_value=False):
            self.assertIsNone(available(OLLAMA, {})[0])

    def test_openart_models_are_split_by_what_they_can_make(self):
        listed = [{"id": "nano-banana-2", "modes": {"image": []}}, {"id": "kling-3-omni", "modes": {"video": []}}]
        with patch("openart_provider.models", return_value=listed):
            self.assertEqual(available(OPENART, {}, kind="image"), (["nano-banana-2"], ""))
            self.assertEqual(available(OPENART, {}, kind="video"), (["kling-3-omni"], ""))

    def test_a_failing_provider_gives_a_note_instead_of_an_error(self):
        with patch("openart_provider.models", side_effect=RuntimeError("not signed in")):
            names, note = available(OPENART, {}, kind="image")
        self.assertIsNone(names)
        self.assertIn("not signed in", note)


if __name__ == "__main__":
    unittest.main()
