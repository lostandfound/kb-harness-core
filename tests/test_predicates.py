"""述語の階層（broader）と標準対応（maps_to）。docs/notes/jutsugo-kaisou-memo.md の三層。"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from kb_harness.cli import main
from kb_harness.doctor import diagnose
from kb_harness.graph import render_graph
from kb_harness.predicates import (
    STANDARD_PREDICATES,
    descendants,
    export_predicates,
    load_predicates,
    nonstandard_layer1,
    refinement_candidates,
    validate_predicates,
)
from kb_harness.project import Project
from kb_harness.validation import validate
from kb_harness.views import load_entities, load_view, query_predicate_matches, resolve_view


BASE_VOCABULARY = (
    "types:\n"
    "  Concept:\n    directory: concepts\n"
    "  Script:\n    directory: scripts\n"
    "predicates:\n"
    "  related-to:\n    description: 未分類\n"
    "  derived-from:\n    description: 派生物→起源\n    domain: [Concept, Script]\n    range: [Concept, Script]\n"
    "    maps_to: [prov:wasDerivedFrom, wdt:P144]\n"
    "  borrowed-from:\n    description: 借用\n    broader: derived-from\n    domain: [Script]\n    range: [Script]\n"
    "tags:\n  - history\n"
)


def _entity(directory: str, slug: str, type_name: str, title: str, relations: str = "[]") -> tuple[str, str]:
    return (
        f"{directory}/{slug}.md",
        f"---\ntype: {type_name}\ntitle: {title}\ndescription: {title} の説明である。\n"
        f"tags: [history]\ntimestamp: 2026-09-01T00:00:00Z\nsources: [Test]\nrelations: {relations}\n"
        f"---\n\n## 概要\n\n本文。\n",
    )


def build_kb(root: Path, vocabulary: str = BASE_VOCABULARY, *, with_views: bool = False) -> Project:
    content = root / "knowledge"
    for directory in ("concepts", "scripts"):
        (content / directory).mkdir(parents=True)
        (content / directory / "index.md").write_text(
            f"---\ntype: Index\ntitle: {directory}\ndescription: 一覧である。\ntags: []\n"
            f"timestamp: 2026-09-01T00:00:00Z\n---\n\n## エンティティ一覧\n\n",
            encoding="utf-8",
        )
    (content / "vocabulary.yml").write_text(vocabulary, encoding="utf-8")
    (content / "references.yml").write_text("{}\n", encoding="utf-8")
    for rel, text in (
        _entity("scripts", "sogdian", "Script", "ソグド文字"),
        _entity("scripts", "uyghur", "Script", "ウイグル文字", "[{predicate: borrowed-from, target: /scripts/sogdian.md}]"),
        _entity("scripts", "mongolian", "Script", "モンゴル文字", "[{predicate: derived-from, target: /scripts/uyghur.md}]"),
        _entity("concepts", "star-schema", "Concept", "スタースキーマ"),
        _entity(
            "concepts", "snowflake", "Concept", "スノーフレークスキーマ",
            "[{predicate: related-to, target: /concepts/star-schema.md}]",
        ),
    ):
        (content / rel).write_text(text, encoding="utf-8")
    for directory in ("concepts", "scripts"):
        links = "\n".join(
            f"- [{p.stem}](/{directory}/{p.name})" for p in sorted((content / directory).glob("*.md")) if p.name != "index.md"
        )
        index = content / directory / "index.md"
        index.write_text(index.read_text(encoding="utf-8") + links + "\n", encoding="utf-8")
    (content / "index.md").write_text(
        "---\ntype: Index\ntitle: root\ndescription: ルートである。\ntags: []\ntimestamp: 2026-09-01T00:00:00Z\n---\n\n"
        "- [concepts](/concepts/index.md)\n- [scripts](/scripts/index.md)\n",
        encoding="utf-8",
    )
    domain = "domain:\n  name: test\n  kb_title: test\n  description: test\n  content_root: knowledge\n"
    if with_views:
        (root / "views").mkdir()
        domain += "views:\n  root: views\n"
    (root / "kb-domain.yml").write_text(domain, encoding="utf-8")
    return Project.discover(root)


class PredicateHierarchyTest(unittest.TestCase):
    def test_load_and_descendants(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            predicates = load_predicates(project.content_root)
            self.assertEqual(predicates["borrowed-from"].broader, "derived-from")
            self.assertEqual(predicates["derived-from"].maps_to, ["prov:wasDerivedFrom", "wdt:P144"])
            self.assertEqual(descendants(predicates, "derived-from"), {"derived-from", "borrowed-from"})
            self.assertEqual(descendants(predicates, "borrowed-from"), {"borrowed-from"})
            self.assertEqual(validate_predicates(predicates), [])

    def test_validate_accepts_well_formed_kb(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            warnings: list[str] = []
            self.assertEqual(validate(project.content_root, warnings=warnings), [])
            self.assertIn("INFO relations: related-to のエッジ 1 件（未分類）", warnings)

    def test_broader_errors(self):
        cases = {
            "未知の述語": "  x:\n    broader: nope\n",
            "自身を指している": "  x:\n    broader: x\n",
            "循環している": "  x:\n    broader: y\n  y:\n    broader: x\n",
            "broader は述語名の文字列": "  x:\n    broader: [a]\n",
            "domain は親 derived-from の domain の部分集合": "  x:\n    broader: derived-from\n    domain: [Nope]\n    range: [Script]\n",
            "range は親 derived-from の range の部分集合": "  x:\n    broader: derived-from\n    domain: [Script]\n",
            "maps_to は空でない文字列のリスト": "  x:\n    maps_to: prov:wasDerivedFrom\n",
        }
        for expected, extra in cases.items():
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tempdir:
                vocabulary = BASE_VOCABULARY.replace("tags:\n", extra + "tags:\n")
                project = build_kb(Path(tempdir), vocabulary)
                errors = validate(project.content_root)
                self.assertTrue(any(expected in error and error.startswith("ERROR /vocabulary.yml") for error in errors), errors)

    def test_unconstrained_parent_allows_any_child(self):
        with tempfile.TemporaryDirectory() as tempdir:
            vocabulary = BASE_VOCABULARY.replace(
                "tags:\n", "  part-of:\n    description: 部分→全体\n  kind-of:\n    broader: part-of\n    domain: [Concept]\n    range: [Concept]\ntags:\n"
            )
            project = build_kb(Path(tempdir), vocabulary)
            self.assertEqual(validate_predicates(load_predicates(project.content_root)), [])

    def test_related_to_cannot_be_a_parent(self):
        # related-to は未分類の印。親にできると層 1 の述語が doctor の目を逃れ、汎化が未分類の件数とずれる
        with tempfile.TemporaryDirectory() as tempdir:
            vocabulary = BASE_VOCABULARY.replace(
                "tags:\n", "  kind-of:\n    broader: related-to\n    domain: [Concept]\n    range: [Concept]\ntags:\n"
            )
            project = build_kb(Path(tempdir), vocabulary)
            predicates = load_predicates(project.content_root)
            errors = validate_predicates(predicates)
            self.assertTrue(any("predicates.kind-of.broader に 'related-to' は使えない" in e for e in errors), errors)
            self.assertEqual(descendants(predicates, "related-to"), {"related-to"})
            self.assertIn("kind-of", nonstandard_layer1(predicates))

    def test_cycle_blames_only_nodes_on_the_cycle(self):
        with tempfile.TemporaryDirectory() as tempdir:
            vocabulary = BASE_VOCABULARY.replace(
                "tags:\n",
                "  x:\n    broader: y\n    domain: [Nope]\n    range: [Script]\n"
                "  y:\n    broader: z\n    domain: [Script]\n    range: [Script]\n"
                "  z:\n    broader: y\n    domain: [Script]\n    range: [Script]\n"
                "tags:\n",
            )
            project = build_kb(Path(tempdir), vocabulary)
            errors = validate_predicates(load_predicates(project.content_root))
            cycles = [e for e in errors if "循環している" in e]
            self.assertEqual(cycles, ["ERROR /vocabulary.yml: predicates の broader が循環している（y → z → y）"])
            # 循環に至るだけの x は循環の責めを負わず、直接の親との包含は検査される
            self.assertTrue(any("predicates.x.domain は親 y の domain の部分集合" in e for e in errors), errors)

    def test_scalar_domain_is_rejected_not_silently_unconstrained(self):
        with tempfile.TemporaryDirectory() as tempdir:
            vocabulary = BASE_VOCABULARY.replace(
                "    broader: derived-from\n    domain: [Script]\n    range: [Script]\n",
                "    broader: derived-from\n    domain: Script\n    range: [Script]\n",
            )
            project = build_kb(Path(tempdir), vocabulary)
            predicates = load_predicates(project.content_root)
            self.assertEqual(predicates["borrowed-from"].domain, ("Script",))
            errors = validate(project.content_root)
            self.assertIn("ERROR /vocabulary.yml: predicates.borrowed-from.domain は型名のリストでなければならない", errors)
            # 1 要素として扱うので、部分集合違反や relation の型制約違反を誤報しない
            self.assertFalse([e for e in errors if "部分集合" in e or "型制約違反" in e], errors)


class RefinementHintTest(unittest.TestCase):
    def test_related_to_edge_with_single_candidate_is_warned(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            predicates = load_predicates(project.content_root)
            # 層 1 で domain / range を持つのは derived-from だけ。borrowed-from は層 2 なので候補にならない
            self.assertEqual(refinement_candidates(predicates, "Concept", "Concept"), ["derived-from"])
            warnings: list[str] = []
            validate(project.content_root, warnings=warnings)
            hints = [w for w in warnings if "精緻化できる" in w]
            self.assertEqual(len(hints), 1)
            self.assertIn("/concepts/snowflake.md: related-to → /concepts/star-schema.md は 'derived-from'", hints[0])

    def test_no_hint_when_candidates_are_ambiguous_or_absent(self):
        with tempfile.TemporaryDirectory() as tempdir:
            vocabulary = BASE_VOCABULARY.replace(
                "tags:\n", "  part-of:\n    domain: [Concept]\n    range: [Concept]\ntags:\n"
            )
            project = build_kb(Path(tempdir), vocabulary)
            warnings: list[str] = []
            validate(project.content_root, warnings=warnings)
            self.assertFalse([w for w in warnings if "精緻化できる" in w], warnings)
            predicates = load_predicates(project.content_root)
            self.assertEqual(refinement_candidates(predicates, None, "Concept"), [])


class ViewGeneralizationTest(unittest.TestCase):
    def test_query_on_parent_predicate_matches_descendant_edges(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            project = build_kb(root, with_views=True)
            view_path = root / "views" / "from-sogdian.yml"
            view_path.write_text(
                "name: ソグド文字系\ndescription: ソグド文字に由来する文字。\nkind: query\n"
                "where:\n  relation: {predicate: derived-from, target: /scripts/sogdian.md}\n",
                encoding="utf-8",
            )
            view = load_view(view_path)
            entities = load_entities(project.content_root)
            # 既定（完全一致）では borrowed-from のエッジは拾わない
            self.assertEqual([m.path for m in resolve_view(view, entities)], [])
            matches = query_predicate_matches(project.content_root)
            self.assertEqual(
                [m.path for m in resolve_view(view, entities, ("Claim", "Index"), matches)],
                ["/scripts/uyghur.md"],
            )
            # graph.json の views も汎化を反映し、predicates で階層を渡す
            graph = json.loads(render_graph(project.content_root, project.views_root))
            self.assertEqual(graph["views"][0]["members"], ["/scripts/uyghur.md"])
            self.assertEqual(graph["predicates"]["borrowed-from"], {"broader": "derived-from"})
            self.assertEqual(graph["predicates"]["derived-from"], {"maps_to": ["prov:wasDerivedFrom", "wdt:P144"]})
            self.assertNotIn("related-to", graph["predicates"])
            # エッジは書かれた葉の述語のまま
            self.assertIn(
                {"source": "/scripts/uyghur.md", "predicate": "borrowed-from", "target": "/scripts/sogdian.md"},
                graph["edges"],
            )


class ViewCliTest(unittest.TestCase):
    def test_view_resolve_generalizes_over_descendants(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            build_kb(root, with_views=True)
            (root / "views" / "from-sogdian.yml").write_text(
                "name: ソグド文字系\ndescription: ソグド文字に由来する文字。\nkind: query\n"
                "where:\n  relation: {predicate: derived-from, target: /scripts/sogdian.md}\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["view", "resolve", "from-sogdian", "--start", str(root), "--format", "json"])
            self.assertEqual(exit_code, 0, output.getvalue())
            payload = json.loads(output.getvalue())
            self.assertEqual([m["path"] for m in payload["members"]], ["/scripts/uyghur.md"])
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["view", "list", "--start", str(root), "--format", "json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["views"][0]["members"], 1)


class GraphExportTest(unittest.TestCase):
    def test_graph_without_hierarchy_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tempdir:
            vocabulary = (
                "types:\n  Concept:\n    directory: concepts\n  Script:\n    directory: scripts\n"
                "predicates:\n  related-to:\n    description: 未分類\n  derived-from:\n    description: 派生\n"
                "  borrowed-from:\n    description: 借用\n"
                "tags:\n  - history\n"
            )
            project = build_kb(Path(tempdir), vocabulary)
            graph = json.loads(render_graph(project.content_root))
            self.assertEqual(sorted(graph), ["claims", "edges", "nodes"])
            self.assertEqual(export_predicates(load_predicates(project.content_root)), {})


class DoctorTest(unittest.TestCase):
    def test_nonstandard_layer1_predicate_is_warned(self):
        with tempfile.TemporaryDirectory() as tempdir:
            vocabulary = BASE_VOCABULARY.replace("tags:\n", "  taught:\n    description: 師→弟子\ntags:\n")
            project = build_kb(Path(tempdir), vocabulary)
            _details, diagnostics = diagnose(project)
            hits = [d for d in diagnostics if d["code"] == "doctor.predicate.nonstandard"]
            self.assertEqual([d["field"] for d in hits], ["predicates.taught"])
            self.assertEqual(hits[0]["severity"], "warning")
            self.assertEqual(hits[0]["context"]["standard"], sorted(STANDARD_PREDICATES))

    def test_standard_and_refined_predicates_pass(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            _details, diagnostics = diagnose(project)
            self.assertFalse([d for d in diagnostics if d["code"] == "doctor.predicate.nonstandard"])


class CliWarningsTest(unittest.TestCase):
    def test_validate_json_exposes_warnings(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            build_kb(root)
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["validate", "--start", str(root), "--format", "json"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["ok"])
            self.assertIn(
                {
                    "severity": "info",
                    "code": "validation.relation.unclassified",
                    "message": "INFO relations: related-to のエッジ 1 件（未分類）",
                },
                payload["warnings"],
            )
            self.assertEqual({w["severity"] for w in payload["warnings"]}, {"info", "warning"})
            self.assertTrue(all(set(w) == {"severity", "code", "message"} for w in payload["warnings"]))

    def test_validate_text_prints_warnings_to_stderr(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            build_kb(root)
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                exit_code = main(["validate", "--start", str(root)])
            self.assertEqual(exit_code, 0)
            self.assertEqual(output.getvalue().strip(), "OK")
            self.assertIn("related-to のエッジ 1 件", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
