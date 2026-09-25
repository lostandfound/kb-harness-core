"""ビュー: エンティティ本文の外に置く束ね（list）と導出（query）。"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from kb_harness.cli import main
from kb_harness.entity import plan_entity_create
from kb_harness.graph import render_graph
from kb_harness.project import Project, ProjectError
from kb_harness.sync import apply_changes_atomically, plan_sync
from kb_harness.views import (
    ViewError,
    load_entities,
    load_view,
    load_views,
    plan_views_index,
    render_views_index,
    resolve_view,
    validate_views,
)


VOCABULARY = (
    "types:\n"
    "  Concept:\n    directory: concepts\n"
    "  Dish:\n    directory: dishes\n"
    "predicates:\n"
    "  part-of:\n    description: 構成要素→全体\n    domain: [Concept, Dish]\n    range: [Concept, Dish]\n"
    "  related-to:\n    description: 汎用\n    domain: [Concept, Dish]\n    range: [Concept, Dish]\n"
    "tags:\n  - cooking\n  - cs\n"
)


def _entity(directory: str, slug: str, type_name: str, title: str, tags: str, relations: str = "[]") -> tuple[str, str]:
    return (
        f"{directory}/{slug}.md",
        f"---\ntype: {type_name}\ntitle: {title}\ndescription: {title} の説明である。\n"
        f"tags: {tags}\ntimestamp: 2026-09-01T00:00:00Z\nsources: [Test]\nrelations: {relations}\n"
        f"---\n\n## 概要\n\n本文。\n",
    )


def build_kb(root: Path, *, with_views_config: bool = True) -> Project:
    content = root / "knowledge"
    for directory in ("concepts", "dishes"):
        (content / directory).mkdir(parents=True)
        (content / directory / "index.md").write_text(
            f"---\ntype: Index\ntitle: {directory}\ndescription: 一覧である。\ntags: []\n"
            f"timestamp: 2026-09-01T00:00:00Z\n---\n\n## エンティティ一覧\n\n",
            encoding="utf-8",
        )
    (content / "vocabulary.yml").write_text(VOCABULARY, encoding="utf-8")
    (content / "references.yml").write_text(
        "ref-a:\n  type: web\n  title: A\n  url: https://example.com/a\n", encoding="utf-8"
    )
    for rel, text in (
        _entity("concepts", "hakka", "Concept", "客家料理", "[cooking]"),
        _entity("concepts", "dry", "Concept", "DRY", "[cs]"),
        _entity("concepts", "semantic-layer", "Concept", "セマンティックレイヤー", "[cs]"),
        _entity(
            "dishes", "meicai", "Dish", "梅菜", "[cooking]",
            "[{predicate: part-of, target: /concepts/hakka.md}]",
        ),
        _entity("dishes", "pasta", "Dish", "パスタ", "[cooking]"),
    ):
        (content / rel).write_text(text, encoding="utf-8")
    config = "domain:\n  content_root: knowledge\n"
    if with_views_config:
        config += "views:\n  root: views\n"
    (root / "kb-domain.yml").write_text(config, encoding="utf-8")
    (root / "views").mkdir()
    (root / "views" / "teigi-once.yml").write_text(
        "name: 一度定義して各所で使う\n"
        "description: 定義を一か所に置く姿勢を共有するもの。\n"
        "kind: list\nbasis: interpretation\n"
        "members:\n"
        "  - /concepts/dry.md\n"
        "  - path: /concepts/semantic-layer.md\n    note: 指標を一度定義する\n",
        encoding="utf-8",
    )
    (root / "views" / "hakka-dishes.yml").write_text(
        "name: 客家料理の料理\ndescription: 客家料理に属する料理。\nkind: query\n"
        "where:\n  type: Dish\n  relation: {predicate: part-of, target: /concepts/hakka.md}\n",
        encoding="utf-8",
    )
    project = Project.from_config(root / "kb-domain.yml")
    apply_changes_atomically(plan_sync(project))
    return project


class ProjectViewsConfigTest(unittest.TestCase):
    def test_views_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
            project = Project.from_config(root / "kb-domain.yml")
            self.assertIsNone(project.views_root)
            self.assertIsNone(project.views_index)

    def test_views_index_defaults_under_root(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\nviews:\n  root: views\n", encoding="utf-8"
            )
            project = Project.from_config(root / "kb-domain.yml")
            self.assertEqual(project.views_root, root / "views")
            self.assertEqual(project.views_index, root / "views" / "index.md")

    def test_views_root_must_be_string(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\nviews:\n  root: 1\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ProjectError, "views.root"):
                Project.from_config(root / "kb-domain.yml")


class LoadViewTest(unittest.TestCase):
    def _load(self, text: str):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "v.yml"
            path.write_text(text, encoding="utf-8")
            return load_view(path)

    def test_list_view_requires_basis(self):
        with self.assertRaisesRegex(ViewError, "basis"):
            self._load("name: n\ndescription: d\nkind: list\nmembers: [/a.md]\n")

    def test_interpretation_must_not_carry_sources(self):
        with self.assertRaisesRegex(ViewError, "interpretation"):
            self._load(
                "name: n\ndescription: d\nkind: list\nbasis: interpretation\n"
                "members: [/a.md]\nsources: ['ref: x']\n"
            )

    def test_source_basis_requires_sources(self):
        with self.assertRaisesRegex(ViewError, "sources"):
            self._load("name: n\ndescription: d\nkind: list\nbasis: source\nmembers: [/a.md]\n")

    def test_query_view_rejects_members(self):
        with self.assertRaisesRegex(ViewError, "members"):
            self._load("name: n\ndescription: d\nkind: query\nwhere: {type: Dish}\nmembers: [/a.md]\n")

    def test_query_view_rejects_unknown_where_key(self):
        with self.assertRaisesRegex(ViewError, "unknown key"):
            self._load("name: n\ndescription: d\nkind: query\nwhere: {title: x}\n")

    def test_unknown_top_level_key_is_rejected(self):
        with self.assertRaisesRegex(ViewError, "unknown key"):
            self._load("name: n\ndescription: d\nkind: query\nwhere: {type: Dish}\nextra: 1\n")


class ResolveAndRenderTest(unittest.TestCase):
    def test_query_view_resolves_by_type_and_relation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            entities = load_entities(project.content_root)
            views = {view.id: view for view in load_views(project.views_root)}
            self.assertEqual(
                [m.path for m in resolve_view(views["hakka-dishes"], entities)],
                ["/dishes/meicai.md"],
            )
            self.assertEqual(
                [(m.path, m.note) for m in resolve_view(views["teigi-once"], entities)],
                [("/concepts/dry.md", ""), ("/concepts/semantic-layer.md", "指標を一度定義する")],
            )

    def test_query_by_tags_is_and_condition(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            (project.views_root / "cs-things.yml").write_text(
                "name: cs\ndescription: cs のもの。\nkind: query\nwhere:\n  tags: [cs]\n", encoding="utf-8"
            )
            entities = load_entities(project.content_root)
            view = {v.id: v for v in load_views(project.views_root)}["cs-things"]
            self.assertEqual(
                [m.path for m in resolve_view(view, entities)],
                ["/concepts/dry.md", "/concepts/semantic-layer.md"],
            )

    def test_render_index_is_deterministic_and_marks_basis(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            first = render_views_index(project.content_root, project.views_root)
            second = render_views_index(project.content_root, project.views_root)
            self.assertEqual(first, second)
            self.assertIn("## 一度定義して各所で使う", first)
            self.assertIn("kind: list / basis: interpretation / 定義: views/teigi-once.yml", first)
            self.assertIn("- [セマンティックレイヤー](/concepts/semantic-layer.md) — 指標を一度定義する", first)
            self.assertIn("## 客家料理の料理", first)
            self.assertIn("- [梅菜](/dishes/meicai.md)", first)
            # 導出ビューはエンティティ本文に書き戻さない
            self.assertNotIn("views", (project.content_root / "dishes" / "meicai.md").read_text(encoding="utf-8"))

    def test_plan_views_index_is_empty_when_disabled_or_in_sync(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            self.assertEqual(plan_views_index(project.content_root, None, None), {})
            self.assertEqual(plan_views_index(project.content_root, project.views_root, project.views_index), {})
            (project.views_root / "teigi-once.yml").write_text(
                "name: 改名\ndescription: d\nkind: list\nbasis: interpretation\nmembers: [/concepts/dry.md]\n",
                encoding="utf-8",
            )
            self.assertEqual(
                list(plan_views_index(project.content_root, project.views_root, project.views_index)),
                [project.views_index.resolve()],
            )


class ValidateViewsTest(unittest.TestCase):
    def test_reports_missing_member_and_unknown_vocabulary(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            (project.views_root / "broken.yml").write_text(
                "name: 壊れ\ndescription: d\nkind: list\nbasis: source\nsources: ['ref: nope']\n"
                "members: [/concepts/missing.md]\n",
                encoding="utf-8",
            )
            (project.views_root / "bad-query.yml").write_text(
                "name: 悪い問い合わせ\ndescription: d\nkind: query\n"
                "where: {type: Nope, tags: [nope], relation: {predicate: nope, target: /concepts/none.md}}\n",
                encoding="utf-8",
            )
            errors = validate_views(project.content_root, project.views_root)
            joined = "\n".join(errors)
            self.assertIn("member '/concepts/missing.md' does not exist", joined)
            self.assertIn("'ref: nope' が references.yml に存在しない", joined)
            self.assertIn("未知の型 'Nope'", joined)
            self.assertIn("未知のタグ 'nope'", joined)
            self.assertIn("未知の述語 'nope'", joined)
            self.assertIn("target '/concepts/none.md' does not exist", joined)

    def test_duplicate_names_and_bad_filenames_are_reported(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            (project.views_root / "Bad_Name.yml").write_text(
                "name: 一度定義して各所で使う\ndescription: d\nkind: list\nbasis: interpretation\n"
                "members: [/concepts/dry.md]\n",
                encoding="utf-8",
            )
            joined = "\n".join(validate_views(project.content_root, project.views_root))
            self.assertIn("ケバブケース", joined)
            self.assertIn("重複", joined)

    def test_clean_kb_has_no_errors(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            self.assertEqual(validate_views(project.content_root, project.views_root), [])

    def test_query_excludes_entities_that_are_not_graph_nodes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            vocabulary = project.content_root / "vocabulary.yml"
            vocabulary.write_text(
                VOCABULARY.replace("predicates:", "  Memo:\n    directory: memos\n    graph: false\npredicates:"),
                encoding="utf-8",
            )
            (project.content_root / "memos").mkdir()
            (project.content_root / "memos" / "note.md").write_text(
                _entity("memos", "note", "Memo", "メモ", "[cs]")[1], encoding="utf-8"
            )
            (project.content_root / "concepts" / "index.md").write_text(
                "---\ntype: Index\ntitle: concepts\ndescription: 一覧である。\ntags: [cs]\n"
                "timestamp: 2026-09-01T00:00:00Z\n---\n\n## エンティティ一覧\n\n",
                encoding="utf-8",
            )
            (project.views_root / "cs-things.yml").write_text(
                "name: cs\ndescription: cs のもの。\nkind: query\nwhere:\n  tags: [cs]\n", encoding="utf-8"
            )
            graph = json.loads(render_graph(project.content_root, project.views_root))
            nodes = {node["path"] for node in graph["nodes"]}
            members = {v["id"]: v["members"] for v in graph["views"]}["cs-things"]
            self.assertEqual(members, ["/concepts/dry.md", "/concepts/semantic-layer.md"])
            self.assertTrue(set(members) <= nodes)


class SyncAndGraphTest(unittest.TestCase):
    def test_graph_carries_views_only_when_configured(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            with_views = json.loads(render_graph(project.content_root, project.views_root))
            without = json.loads(render_graph(project.content_root))
            self.assertNotIn("views", without)
            self.assertEqual(
                [(v["id"], v["kind"], v["members"]) for v in with_views["views"]],
                [
                    ("hakka-dishes", "query", ["/dishes/meicai.md"]),
                    ("teigi-once", "list", ["/concepts/dry.md", "/concepts/semantic-layer.md"]),
                ],
            )
            self.assertEqual(with_views["views"][1]["basis"], "interpretation")
            self.assertEqual(with_views["views"][0]["where"]["type"], "Dish")

    def test_sync_generates_views_index_and_check_detects_staleness(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            self.assertTrue(project.views_index.is_file())
            self.assertEqual(plan_sync(project), {})
            (project.views_root / "pasta-only.yml").write_text(
                "name: パスタだけ\ndescription: d\nkind: list\nbasis: interpretation\nmembers: [/dishes/pasta.md]\n",
                encoding="utf-8",
            )
            stale = plan_sync(project)
            self.assertEqual(
                sorted(str(p.relative_to(project.repo_root)) for p in stale),
                ["graph.json", "views/index.md"],
            )

    def test_entity_create_keeps_views_in_sync(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            project = build_kb(root)
            spec = root / "spec.yml"
            spec.write_text(
                "type: Dish\nslug: yanju\ntitle: 塩焗鶏\ndescription: 客家の鶏料理である。\n"
                "tags: [cooking]\nsources: [Test]\n"
                "relations:\n  - predicate: part-of\n    target: /concepts/hakka.md\n"
                "sections:\n  概要: 概要である。\n  詳細: 詳細である。\n  関連項目: なし。\n",
                encoding="utf-8",
            )
            plan = plan_entity_create(project, spec, timestamp="2026-09-02T00:00:00Z")
            changed = {str(path.relative_to(root)) for path in plan.changes}
            self.assertIn("views/index.md", changed)
            self.assertIn("graph.json", changed)
            new_index = plan.changes[project.views_index.resolve()]
            self.assertIn("- [塩焗鶏](/dishes/yanju.md)", new_index)


class BrokenViewTest(unittest.TestCase):
    """形式不備のビューがあっても、生成系は内部エラーでなくビューの診断で止まる。"""

    def _run(self, project: Project, *argv: str) -> tuple[int, dict]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([*argv, "--start", str(project.repo_root), "--format", "json"])
        return code, json.loads(buffer.getvalue())

    def _broken(self, root: Path) -> Project:
        project = build_kb(root)
        (project.views_root / "broken.yml").write_text("name: 壊れた\nkind: list\n", encoding="utf-8")
        return project

    def test_sync_and_graph_build_report_view_diagnostic(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = self._broken(Path(tempdir).resolve())
            for argv in (("sync",), ("graph", "build")):
                code, result = self._run(project, *argv)
                self.assertEqual(code, 1, argv)
                codes = [d["code"] for d in result["diagnostics"]]
                self.assertNotIn("internal.error", codes, argv)
                self.assertTrue(all(c.startswith("view.") for c in codes), codes)
                self.assertIn("broken.yml", result["diagnostics"][0]["message"])

    def test_entity_create_reports_view_errors_as_validation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir).resolve()
            project = self._broken(root)
            spec = root / "spec.yml"
            spec.write_text(
                "type: Dish\nslug: yanju\ntitle: 塩焗鶏\ndescription: 客家の鶏料理である。\n"
                "tags: [cooking]\nsources: [Test]\n"
                "sections:\n  概要: 概要である。\n  詳細: 詳細である。\n  関連項目: なし。\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(Exception, "broken.yml") as caught:
                plan_entity_create(project, spec, timestamp="2026-09-02T00:00:00Z")
            self.assertNotIsInstance(caught.exception, ViewError)


class StagedViewsTest(unittest.TestCase):
    def test_views_root_that_contains_content_root_is_staged(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir).resolve()
            project = build_kb(root)
            # content_root を kb/entities、views.root を kb に置く（content の外なので許される）
            kb = root / "kb"
            kb.mkdir()
            project.content_root.rename(kb / "entities")
            for name in ("teigi-once.yml", "hakka-dishes.yml"):
                (project.views_root / name).rename(kb / name)
            shutil.rmtree(project.views_root)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: kb/entities\nviews:\n  root: kb\n  index: views.md\n", encoding="utf-8"
            )
            project = Project.from_config(root / "kb-domain.yml")
            apply_changes_atomically(plan_sync(project))
            spec = root / "spec.yml"
            spec.write_text(
                "type: Dish\nslug: yanju\ntitle: 塩焗鶏\ndescription: 客家の鶏料理である。\n"
                "tags: [cooking]\nsources: [Test]\n"
                "relations:\n  - predicate: part-of\n    target: /concepts/hakka.md\n"
                "sections:\n  概要: 概要である。\n  詳細: 詳細である。\n  関連項目: なし。\n",
                encoding="utf-8",
            )
            plan = plan_entity_create(project, spec, timestamp="2026-09-02T00:00:00Z")
            graph = json.loads(plan.changes[(root / "graph.json").resolve()])
            members = {v["id"]: v["members"] for v in graph["views"]}["hakka-dishes"]
            self.assertIn("/dishes/yanju.md", members)


class ViewCliTest(unittest.TestCase):
    def _run(self, project: Project, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([*argv, "--start", str(project.repo_root)])
        return code, buffer.getvalue()

    def test_list_resolve_validate(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            code, out = self._run(project, "view", "list", "--format", "json")
            self.assertEqual(code, 0)
            listed = json.loads(out)["views"]
            self.assertEqual([(v["id"], v["members"]) for v in listed], [("hakka-dishes", 1), ("teigi-once", 2)])

            code, out = self._run(project, "view", "resolve", "teigi-once", "--format", "json")
            self.assertEqual(code, 0)
            self.assertEqual(
                [m["path"] for m in json.loads(out)["members"]],
                ["/concepts/dry.md", "/concepts/semantic-layer.md"],
            )

            code, _ = self._run(project, "view", "resolve", "nope")
            self.assertEqual(code, 1)

            code, _ = self._run(project, "view", "validate")
            self.assertEqual(code, 0)
            code, _ = self._run(project, "validate")
            self.assertEqual(code, 0)

    def test_kb_validate_reports_view_errors(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            (project.views_root / "broken.yml").write_text(
                "name: x\ndescription: d\nkind: list\nbasis: interpretation\nmembers: [/concepts/none.md]\n",
                encoding="utf-8",
            )
            code, out = self._run(project, "validate", "--format", "json")
            self.assertEqual(code, 1)
            self.assertIn("/concepts/none.md", out)
            code, out = self._run(project, "sync", "--check", "--format", "json")
            self.assertEqual(code, 1)
            self.assertIn("views.stale", out)

    def test_view_commands_fail_cleanly_when_disabled(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir), with_views_config=False)
            code, _ = self._run(project, "view", "list")
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()


class ProjectViewsSafetyTest(unittest.TestCase):
    """views.root / views.index はリポジトリ内、content_root の外、生成物と衝突しない。"""

    def _project(self, views_section: str) -> Project:
        root = Path(self._tempdir.name)
        (root / "kb-domain.yml").write_text(
            f"domain:\n  content_root: knowledge\nviews:\n{views_section}", encoding="utf-8"
        )
        return Project.from_config(root / "kb-domain.yml")

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tempdir.cleanup()

    def test_rejects_paths_escaping_repo_root(self):
        with self.assertRaisesRegex(ProjectError, "inside the repository root"):
            self._project("  root: ../elsewhere\n")
        with self.assertRaisesRegex(ProjectError, "inside the repository root"):
            self._project("  root: views\n  index: /tmp/index.md\n")

    def test_rejects_views_inside_content_root(self):
        with self.assertRaisesRegex(ProjectError, "content_root"):
            self._project("  root: knowledge/views\n")
        with self.assertRaisesRegex(ProjectError, "content_root"):
            self._project("  root: views\n  index: knowledge/index.md\n")

    def test_rejects_index_colliding_with_generated_or_config_files(self):
        with self.assertRaisesRegex(ProjectError, "distinct"):
            self._project("  root: views\n  index: graph.json\n")
        with self.assertRaisesRegex(ProjectError, "distinct"):
            self._project("  root: views\n  index: kb-domain.yml\n")
        with self.assertRaisesRegex(ProjectError, "distinct"):
            self._project("  root: views\n  index: views/all.yml\n")

    def test_accepts_index_outside_views_root(self):
        project = self._project("  root: views\n  index: docs/views.md\n")
        self.assertEqual(project.views_index, (Path(self._tempdir.name) / "docs" / "views.md").resolve())


class DuplicateViewIdTest(unittest.TestCase):
    def test_same_stem_in_yml_and_yaml_is_rejected(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            (project.views_root / "teigi-once.yaml").write_text(
                "name: 別名\ndescription: d\nkind: list\nbasis: interpretation\nmembers: [/concepts/dry.md]\n",
                encoding="utf-8",
            )
            joined = "\n".join(validate_views(project.content_root, project.views_root))
            self.assertIn("view id 'teigi-once' が重複している", joined)
            with self.assertRaisesRegex(ViewError, "duplicate view id"):
                load_views(project.views_root)


class GraphCommandViewsTest(unittest.TestCase):
    """kb graph build / check は sync と同じ graph.json（views 付き）を作る。"""

    def _run(self, project: Project, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([*argv, "--start", str(project.repo_root)])
        return code, buffer.getvalue()

    def test_graph_check_agrees_with_sync_and_build_emits_views(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            code, _ = self._run(project, "graph", "check")
            self.assertEqual(code, 0)
            (project.repo_root / "graph.json").write_text("{}\n", encoding="utf-8")
            code, _ = self._run(project, "graph", "build")
            self.assertEqual(code, 0)
            graph = json.loads((project.repo_root / "graph.json").read_text(encoding="utf-8"))
            self.assertEqual([v["id"] for v in graph["views"]], ["hakka-dishes", "teigi-once"])
            self.assertEqual(plan_sync(project), {})

    def test_export_graph_script_emits_views(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tempdir:
            project = build_kb(Path(tempdir))
            script = Path(__file__).resolve().parents[1] / "scripts" / "export_graph.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(project.content_root)],
                capture_output=True, text=True, check=True,
            )
            self.assertIn('"views"', result.stdout)
            self.assertIn('"hakka-dishes"', result.stdout)
