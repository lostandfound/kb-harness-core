import unittest

from kb_harness.diagnostics import HarnessError
from kb_harness.markdown import parse_document


class MarkdownTest(unittest.TestCase):
    def test_parses_frontmatter_and_body(self):
        document = parse_document(
            "example.md",
            "---\ntype: Person\ntitle: Example\n---\n\n# Example\n",
        )

        self.assertEqual(document.frontmatter["type"], "Person")
        self.assertEqual(document.frontmatter["title"], "Example")
        self.assertEqual(document.body, "# Example\n")

    def test_rejects_document_without_frontmatter(self):
        with self.assertRaises(HarnessError) as raised:
            parse_document("example.md", "# Example\n")

        self.assertEqual(
            raised.exception.diagnostic.code,
            "markdown.frontmatter_missing",
        )

    def test_rejects_frontmatter_that_is_not_a_mapping(self):
        with self.assertRaises(HarnessError) as raised:
            parse_document("example.md", "---\n- Person\n---\nBody\n")

        self.assertEqual(
            raised.exception.diagnostic.code,
            "markdown.frontmatter_not_mapping",
        )


if __name__ == "__main__":
    unittest.main()
