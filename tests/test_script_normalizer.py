import unittest
from services.script_service import ScriptNormalizer

class TestScriptNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = ScriptNormalizer()

    def test_whitespace_and_punctuation_cleanup(self):
        raw = "This is a   sentence  with  excessive   spaces ,and bad punctuation ..  next sentence .."
        cleaned, warnings = self.normalizer.normalize(raw)
        self.assertNotIn("   ", cleaned)
        self.assertIn("spaces, and bad punctuation.", cleaned)

    def test_html_entity_unescaping(self):
        raw = "They said &quot;the truth is revealed&quot; &amp; it was undeniable."
        cleaned, warnings = self.normalizer.normalize(raw)
        self.assertIn('"the truth is revealed" & it was undeniable.', cleaned)

    def test_religious_reference_verification_warning(self):
        raw = "The Prophet said to love for your brother what you love for yourself."
        cleaned, warnings = self.normalizer.normalize(raw)
        self.assertTrue(any("Religious citation/reference detected" in w for w in warnings))

    def test_non_religious_content_no_warning(self):
        raw = "Deep sea bioluminescence produces vibrant lights in the oceanic trench."
        cleaned, warnings = self.normalizer.normalize(raw)
        self.assertEqual(len(warnings), 0)

if __name__ == "__main__":
    unittest.main()
