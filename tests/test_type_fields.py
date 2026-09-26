"""型固有フィールド（extra_fields / optional_fields）の検査と entity create の挙動。"""
import tempfile
import unittest
from pathlib import Path

from kb_harness.entity import EntitySpecError, plan_entity_create
from kb_harness.markdown import field_text
from kb_harness.project import Project
from kb_harness.validation import validate

INDEX = (
    "---\ntype: Index\ntitle: {title}\ndescription: 一覧である。\ntags: [index]\n"
    "timestamp: 2026-09-01T00:00:00Z\n---\n\n## エンティティ一覧\n\n{links}"
)


def _person(fields: str) -> str:
    return (
        "---\ntype: Person\ntitle: 人物\ndescription: 人物である。\ntags: []\n"
        "timestamp: 2026-09-01T00:00:00Z\nsources: ['https://example.org/']\n"
        f"{fields}---\n\n## 概要\n\n本文である。\n"
    )


def build_kb(root: Path, vocabulary: str, person_fields: str | None = "born: '1940'\n") -> Path:
    content = root / "knowledge"
    (content / "people").mkdir(parents=True, exist_ok=True)
    (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
    (content / "vocabulary.yml").write_text(vocabulary, encoding="utf-8")
    (content / "references.yml").write_text("{}\n", encoding="utf-8")
    links = ""
    if person_fields is not None:
        (content / "people" / "x.md").write_text(_person(person_fields), encoding="utf-8")
        links = "- [x](/people/x.md)\n"
    (content / "people" / "index.md").write_text(INDEX.format(title="人物", links=links), encoding="utf-8")
    (content / "index.md").write_text(INDEX.format(title="root", links="- [people](/people/index.md)\n"), encoding="utf-8")
    return content


VOCAB = (
    "types:\n  Person:\n    directory: people\n"
    "    extra_fields: [born]\n    optional_fields: [died, year]\n    sections: [概要]\n"
    "predicates:\n  related-to:\n    description: 関連\n"
    "tags: [index]\n"
)


class FieldTextTest(unittest.TestCase):
    def test_scalars_map_to_text_and_others_to_none(self):
        from datetime import date, datetime

        self.assertEqual(field_text(" 1940 "), "1940")
        self.assertEqual(field_text(2021), "2021")
        self.assertEqual(field_text(date(2021, 5, 1)), "2021-05-01")
        self.assertEqual(field_text(datetime(2021, 5, 1, 0, 0)), "2021-05-01T00:00:00")
        for value in ("", "  ", None, True, False, [], {}):
            self.assertIsNone(field_text(value), value)


class ValidateFieldsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self, vocabulary=VOCAB, person_fields="born: '1940'\n"):
        content = build_kb(self.root, vocabulary, person_fields)
        return [e for e in validate(content) if "/people/x.md" in e or "vocabulary.yml" in e]

    def test_optional_field_may_be_omitted(self):
        self.assertEqual(self.errors(), [])

    def test_required_field_still_required(self):
        self.assertEqual(self.errors(person_fields="died: '2000'\n"), ["ERROR /people/x.md: missing required field 'born'"])

    def test_optional_field_present_is_checked(self):
        self.assertEqual(self.errors(person_fields="born: '1940'\ndied: ''\n"),
                         ["ERROR /people/x.md: 'died' は非空の文字列でなければならない（値: ''）"])
        self.assertEqual(self.errors(person_fields="born: '1940'\ndied: 前200\n"),
                         ["ERROR /people/x.md: 'died' の形式が不正 '前200'"])

    def test_unquoted_numbers_and_dates_are_strings(self):
        self.assertEqual(self.errors(person_fields="born: 1940\nyear: 2021\n"), [])
        self.assertEqual(self.errors(person_fields="born: '1940'\nyear: 2021-05-01\n"), [])

    def test_non_scalar_value_gets_accurate_message(self):
        self.assertEqual(self.errors(person_fields="born: [1940]\n"),
                         ["ERROR /people/x.md: 'born' は非空の文字列でなければならない（値: [1940]）"])

    def test_vocabulary_overlap_and_shape_are_rejected(self):
        bad = VOCAB.replace("optional_fields: [died, year]", "optional_fields: [born, died]")
        self.assertIn("ERROR vocabulary.yml: types.Person で extra_fields と optional_fields に同じフィールドがある: born", self.errors(bad))
        bad = VOCAB.replace("optional_fields: [died, year]", "optional_fields: died")
        self.assertIn("ERROR vocabulary.yml: types.Person.optional_fields はフィールド名のリストでなければならない", self.errors(bad))


class EntityCreateFieldsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        build_kb(self.root, VOCAB, person_fields=None)
        self.project = Project.discover(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self, fields: str) -> Path:
        path = self.root / "entity.yml"
        path.write_text(
            "type: Person\nslug: alan\ntitle: アラン\ndescription: 人物である。\ntags: [index]\n"
            "sources: ['https://example.org/']\nsections:\n  概要: |\n    本文である。\n"
            f"{fields}",
            encoding="utf-8",
        )
        return path

    def created(self, fields: str) -> str:
        plan = plan_entity_create(self.project, self.spec(fields), timestamp="2026-09-01T00:00:00Z")
        (text,) = [t for p, t in plan.changes.items() if p.name == "alan.md"]
        return text

    def test_optional_omitted_and_present(self):
        text = self.created("fields:\n  born: '1940'\n")
        self.assertIn("born: '1940'\n", text)
        self.assertNotIn("died", text)
        text = self.created("fields:\n  born: 1940\n  died: 2000\n")
        self.assertIn("born: '1940'\n", text)
        self.assertIn("died: '2000'\n", text)

    def test_type_without_sections_gets_default_sections_regardless_of_name(self):
        vocab = VOCAB.replace("    sections: [概要]\n", "")
        (self.root / "knowledge" / "vocabulary.yml").write_text(vocab, encoding="utf-8")
        with self.assertRaisesRegex(EntitySpecError, "missing sections: 詳細, 関連項目"):
            self.created("fields:\n  born: '1940'\n")

    def test_required_and_unknown_fields(self):
        with self.assertRaisesRegex(EntitySpecError, "missing required field 'born'"):
            self.created("fields:\n  died: '2000'\n")
        with self.assertRaisesRegex(EntitySpecError, "unknown field"):
            self.created("fields:\n  born: '1940'\n  jobTitle: 教授\n")
        with self.assertRaisesRegex(EntitySpecError, "field 'died' must be a non-empty string"):
            self.created("fields:\n  born: '1940'\n  died: ''\n")


if __name__ == "__main__":
    unittest.main()
