import unittest

from shot_rules import SHOT_RULES


class ShotRulesTest(unittest.TestCase):
    def test_lying_rule_names_the_helper_and_the_cause(self):
        self.assertIn('restOn', SHOT_RULES)
        self.assertIn('HIP', SHOT_RULES)
        self.assertIn("'/engine/rig2d.js'", SHOT_RULES)

    def test_text_only_and_review_rules_present(self):
        self.assertIn('only text', SHOT_RULES)
        self.assertIn('contact sheets', SHOT_RULES)

    def test_studio_prompt_includes_rules(self):
        import re
        from pathlib import Path
        source = Path(__file__).with_name('studio_gui.py').read_text(encoding='utf-8')
        self.assertTrue(re.search(r'\{SHOT_RULES\}', source))
        self.assertIn('from shot_rules import SHOT_RULES', source)


if __name__ == '__main__':
    unittest.main()
