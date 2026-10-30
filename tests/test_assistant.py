import unittest

from moss_go.assistant import PromptAssistant, validate_suggestion
from moss_go.errors import StudioError
from moss_go.characters import compose_prompt


class AssistantTests(unittest.TestCase):
    def test_existing_canonical_traits_are_not_appended_again(self):
        character = {"hair": "short silver hair", "eyes": "green eyes"}
        result = compose_prompt("A courier with short silver hair and green eyes.", character)
        self.assertEqual(result, "A courier with short silver hair and green eyes.")
    def test_helper_cannot_silently_send_prompts_to_external_servers(self):
        for url in ("https://api.example.com", "http://192.168.1.2:11434", "http://user@127.0.0.1:11434", "http://localhost:11434?redirect=remote"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                PromptAssistant(url)

    def test_quoted_visible_text_is_preserved_verbatim(self):
        with self.assertRaises(StudioError):
            validate_suggestion('A sign saying "Тихая мастерская"', 'A workshop sign saying "Quiet Workshop"')
        self.assertIn("Тихая мастерская", validate_suggestion('A sign saying "Тихая мастерская"', 'A simple sign reading "Тихая мастерская", painted on wood.'))

    def test_numbers_and_locked_traits_cannot_disappear(self):
        with self.assertRaises(StudioError):
            validate_suggestion("3 orange birds", "A flock of orange birds")
        with self.assertRaises(StudioError):
            validate_suggestion("A courier", "A courier in a yellow coat", {"hair": "short silver hair"})

    def test_an_unrequested_caption_cannot_be_added_to_a_minimal_brief(self):
        with self.assertRaises(StudioError):
            validate_suggestion("A black ink drawing of a lighthouse.", 'A black ink drawing of a lighthouse. "Lighthouse"')

    def test_reasoning_or_code_blocks_are_not_applied_as_prompts(self):
        for reply in ("<think>Let me think</think>A picture", "```text\nA picture\n```"):
            with self.subTest(reply=reply), self.assertRaises(StudioError):
                validate_suggestion("A picture", reply)


if __name__ == "__main__":
    unittest.main()
