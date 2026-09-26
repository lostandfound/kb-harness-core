"""vocabulary.yml の名前の文字種の検査。"""
import unittest

from kb_harness.naming import validate_vocabulary_names


class VocabularyNamingTest(unittest.TestCase):
    def test_conforming_vocabulary_has_no_problems(self):
        data = {
            "types": {"Person": {"extra_fields": ["born"], "optional_fields": ["died", "same_as"]}, "HistoricalEvent": {}, "Index": {}, "Claim": {}},
            "predicates": {"related-to": {}, "part-of": {}, "taught": {}},
            "properties": {"established-year": {}},
            "tags": ["cs", "machine-learning", "index"],
        }
        self.assertEqual(validate_vocabulary_names(data), [])

    def test_each_kind_is_checked(self):
        data = {
            "types": {"person": {}, "Historical-Event": {}, "Work": {"optional_fields": ["sameAs", "same-as"]}},
            "predicates": {"createdBy": {}, "Part-Of": {}, "part_of": {}},
            "properties": {"birthYear": {}, "birth_year": {}},
            "tags": ["CS", "machine_learning"],
        }
        problems = validate_vocabulary_names(data)
        self.assertEqual(
            [p.split(" ")[0] for p in problems],
            ["types.person", "types.Historical-Event", "predicates.createdBy", "predicates.Part-Of", "predicates.part_of",
             "properties.birthYear", "properties.birth_year", "types.Work.optional_fields", "types.Work.optional_fields", "tags", "tags"],
        )

    def test_missing_sections_are_ignored(self):
        self.assertEqual(validate_vocabulary_names({}), [])
        self.assertEqual(validate_vocabulary_names({"types": None, "tags": "cs"}), [])


if __name__ == "__main__":
    unittest.main()
