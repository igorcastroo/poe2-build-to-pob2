import unittest

from gui import TEXT


class GuiLocalizationTests(unittest.TestCase):
    def test_languages_have_the_same_interface_keys(self):
        self.assertEqual(set(TEXT["pt-BR"]), set(TEXT["en-US"]))

    def test_english_only_translates_visible_copy(self):
        self.assertNotEqual(TEXT["pt-BR"]["generate"], TEXT["en-US"]["generate"])


if __name__ == "__main__":
    unittest.main()
