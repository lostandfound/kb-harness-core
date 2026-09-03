import pytest

import kb_harness.okf as okf
from pathlib import Path

import yaml

from kb_harness.okf import (
    OkfExportError,
    plan_okf_export,
    render_okf_concept,
    render_okf_index,
    validate_okf_bundle,
)
from kb_harness.project import Project


def _project(tmp_path: Path, files: dict[str, str], registry: object = None) -> Project:
    content = tmp_path / "content"
    content.mkdir()
    for name, text in files.items():
        path = content / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if registry is not None:
        (content / "references.yml").write_text(
            yaml.safe_dump(registry, allow_unicode=True, sort_keys=True), encoding="utf-8"
        )
    return Project(repo_root=tmp_path, content_root=content)


def test_plan_okf_export_walks_and_renders_bundle(tmp_path):
    project = _project(tmp_path, {
        "index.md": "---\ntitle: KB\n---\n# KB\n",
        "branch/index.md": "---\ntype: Index\n---\n# Branch\n",
        "branch/thing.md": "---\ntype: Concept\ntitle: Thing\n---\nBody\n",
    })
    result = plan_okf_export(project, tmp_path / "out")
    assert list(result) == [
        tmp_path / "out/branch/index.md",
        tmp_path / "out/branch/thing.md",
        tmp_path / "out/index.md",
    ]
    assert "okf_version: '0.2'" in result[tmp_path / "out/index.md"]
    assert result[tmp_path / "out/branch/index.md"] == "# Branch\n"


def test_plan_okf_export_resolves_sources_and_emits_reference(tmp_path):
    project = _project(tmp_path, {
        "thing.md": "---\ntype: Concept\ntitle: Thing\nsources:\n  - 'ref: book'\n  - https://example.test/a\n  - field notes\n  - {resource: /local, confidence: high}\n---\nBody\n",
    }, {"book": {"type": "book", "title": "A Book", "url": "https://book.test", "author": "A"}})
    result = plan_okf_export(project, tmp_path / "out")
    text = result[tmp_path / "out/thing.md"]
    assert "resource: /references/book.md" in text
    assert "resource: https://example.test/a" in text
    assert "resource: field notes" in text
    assert "confidence: high" in text
    reference = result[tmp_path / "out/references/book.md"]
    assert "type: Reference" in reference
    assert "reference_type: book" in reference
    assert "resource: https://book.test" in reference
    assert "author: A" in reference


@pytest.mark.parametrize("ref_id", ["../../escaped", "../x", "a/b", "/absolute", "", "."])
def test_plan_okf_export_rejects_invalid_reference_ids(tmp_path, ref_id):
    project = _project(
        tmp_path,
        {"thing.md": f"---\ntype: Concept\nsources:\n - 'ref: {ref_id}'\n---\n"},
        {ref_id: {"title": "Unexpected"}},
    )

    with pytest.raises(OkfExportError) as raised:
        plan_okf_export(project, tmp_path / "out")

    assert raised.value.code == "okf.source.ref_id_invalid"


def test_plan_okf_export_preserves_log_body(tmp_path):
    project = _project(tmp_path, {"log.md": "---\ntitle: Log\n---\n# History\n"})
    result = plan_okf_export(project, tmp_path / "out")
    assert result[tmp_path / "out/log.md"] == "# History\n"


@pytest.mark.parametrize("target_kind", ["external", "internal"])
def test_plan_okf_export_rejects_markdown_symlink(tmp_path, target_kind):
    project = _project(tmp_path, {"target.md": "---\ntype: Concept\n---\nBody\n"})
    target = tmp_path / "outside.md" if target_kind == "external" else project.content_root / "target.md"
    if target_kind == "external":
        target.write_text("---\ntype: Concept\n---\nOutside\n", encoding="utf-8")
    link = project.content_root / "linked.md"
    link.symlink_to(target)

    with pytest.raises(OkfExportError) as raised:
        plan_okf_export(project, tmp_path / "out")

    assert raised.value.code == "okf.input.symlink"


def test_plan_okf_export_does_not_follow_symlink_directory(tmp_path):
    project = _project(tmp_path, {"thing.md": "---\ntype: Concept\n---\nBody\n"})
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.md").write_text("---\ntype: Concept\n---\nSecret\n", encoding="utf-8")
    (project.content_root / "linked").symlink_to(external, target_is_directory=True)

    result = plan_okf_export(project, tmp_path / "out")

    assert all("secret.md" not in path.as_posix() for path in result)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("---\ntitle: Nested log\n---\n# History\n", "# History\n"),
        ("# History\n", "# History\n"),
    ],
)
def test_plan_okf_export_treats_nested_log_as_reserved(tmp_path, source, expected):
    project = _project(tmp_path, {"nested/log.md": source})

    result = plan_okf_export(project, tmp_path / "out")

    assert result[tmp_path / "out/nested/log.md"] == expected


@pytest.mark.parametrize("files, registry, code", [
    ({"thing.md": "---\ntype: Concept\nsources:\n - 'ref: missing'\n---\n"}, {}, "okf.source.ref_not_found"),
    ({"thing.md": "---\ntype: Concept\nsources: nope\n---\n"}, None, "okf.sources.not_list"),
    ({"thing.md": "---\ntype: Concept\nsources:\n - 4\n---\n"}, None, "okf.source.invalid"),
    ({"thing.md": "---\ntype: Concept\nsources:\n - {title: no-resource}\n---\n"}, None, "okf.source.resource_required"),
])
def test_plan_okf_export_rejects_invalid_sources(tmp_path, files, registry, code):
    project = _project(tmp_path, files, registry)
    with pytest.raises(OkfExportError) as raised:
        plan_okf_export(project, tmp_path / "out")
    assert raised.value.code == code


def test_plan_okf_export_rejects_invalid_registry(tmp_path):
    project = _project(tmp_path, {"thing.md": "---\ntype: Concept\nsources:\n - 'ref: book'\n---\n"}, [])
    with pytest.raises(OkfExportError) as raised:
        plan_okf_export(project, tmp_path / "out")
    assert raised.value.code == "okf.references.not_mapping"


def test_plan_okf_export_rejects_missing_registry(tmp_path):
    project = _project(tmp_path, {"thing.md": "---\ntype: Concept\nsources:\n - 'ref: book'\n---\n"})
    with pytest.raises(OkfExportError) as raised:
        plan_okf_export(project, tmp_path / "out")
    assert raised.value.code == "okf.references.missing"


def test_plan_okf_export_rejects_non_mapping_registry_entry(tmp_path):
    project = _project(tmp_path, {"thing.md": "---\ntype: Concept\nsources:\n - 'ref: book'\n---\n"}, {"book": "not a mapping"})
    with pytest.raises(OkfExportError) as raised:
        plan_okf_export(project, tmp_path / "out")
    assert raised.value.code == "okf.references.entry_not_mapping"


def test_plan_okf_export_does_not_write_and_is_repeatable(tmp_path):
    project = _project(tmp_path, {"thing.md": "---\ntype: Concept\n---\nBody\n"})
    output = tmp_path / "out"
    first = plan_okf_export(project, output)
    second = plan_okf_export(project, output)
    assert first == second
    assert not output.exists()


def test_plan_okf_export_is_deterministic_and_detects_collision(tmp_path):
    project = _project(tmp_path, {
        "thing.md": "---\ntype: Concept\nsources:\n - 'ref: book'\n---\n",
        "references/book.md": "---\ntype: Concept\n---\n# Existing\n",
    }, {"book": {"title": "Book"}})
    with pytest.raises(OkfExportError) as raised:
        plan_okf_export(project, tmp_path / "out")
    assert raised.value.code == "okf.output.collision"


def test_render_okf_concept_preserves_frontmatter_and_body_deterministically():
    # Given a concept document with known and unknown frontmatter keys.
    source = "---\ntype: Concept\ntitle: 拳\nzeta: 2\nalpha: 1\n---\n本文です。\n"

    # When it is rendered as an OKF concept.
    rendered = render_okf_concept("concept.md", source)

    # Then frontmatter is stable and the body is preserved.
    assert rendered == "---\nalpha: 1\ntitle: 拳\ntype: Concept\nzeta: 2\n---\n本文です。\n"


def test_render_okf_claim_maps_internal_status():
    # Given a Claim using the internal status vocabulary.
    source = "---\ntype: Claim\nstatus: accepted\ntitle: 命題\n---\n本文です。\n"

    # When it is rendered as an OKF concept.
    rendered = render_okf_concept("claim.md", source)

    # Then claim_status preserves the internal state and status is lifecycle state.
    assert "claim_status: accepted\n" in rendered
    assert "status: stable\n" in rendered


def test_render_okf_claim_rejects_existing_claim_status():
    # Given a Claim with two competing status fields.
    source = "---\ntype: Claim\nstatus: accepted\nclaim_status: proposed\n---\n本文\n"

    # When it is rendered as an OKF concept.
    with pytest.raises(OkfExportError) as raised:
        render_okf_concept("claim.md", source)

    # Then the stable domain error code identifies the collision.
    assert raised.value.code == "okf.claim_status.conflict"


def test_render_okf_claim_rejects_unknown_internal_status():
    # Given a Claim with an unsupported internal status.
    source = "---\ntype: Claim\nstatus: unknown\n---\n本文\n"

    # When it is rendered as an OKF concept.
    with pytest.raises(OkfExportError) as raised:
        render_okf_concept("claim.md", source)

    # Then the stable domain error code identifies the invalid value.
    assert raised.value.code == "okf.claim_status.invalid"


def test_render_okf_concept_requires_non_empty_type():
    # Given a document without a usable type.
    source = "---\ntitle: 型なし\ntype: ''\n---\n本文\n"

    # When it is rendered as an OKF concept.
    with pytest.raises(OkfExportError) as raised:
        render_okf_concept("concept.md", source)

    # Then the stable domain error code identifies the missing type.
    assert raised.value.code == "okf.type.required"


def test_render_okf_concept_moves_legacy_timestamp_to_internal_timestamp():
    source = "---\ntype: Concept\ntimestamp: 2024-01-02 03:04:05\n---\n本文\n"
    rendered = render_okf_concept("concept.md", source)
    assert "\ntimestamp:" not in rendered
    assert "internal_timestamp: '2024-01-02T03:04:05'" in rendered


def test_render_okf_concept_rejects_timestamp_collision():
    source = "---\ntype: Concept\ntimestamp: 2024-01-02\ninternal_timestamp: old\n---\n本文\n"
    with pytest.raises(OkfExportError) as raised:
        render_okf_concept("concept.md", source)
    assert raised.value.code == "okf.timestamp.conflict"


def test_render_okf_concept_serializes_offset_timestamp():
    source = "---\ntype: Concept\ntimestamp: 2024-01-02 03:04:05+09:00\n---\n本文\n"
    rendered = render_okf_concept("concept.md", source)
    assert "internal_timestamp: '2024-01-02T03:04:05+09:00'" in rendered


def test_plan_okf_export_moves_timestamp_for_concept_output(tmp_path):
    project = _project(
        tmp_path,
        {"thing.md": "---\ntype: Concept\ntimestamp: 2024-01-02\n---\n本文\n"},
    )
    result = plan_okf_export(project, tmp_path / "out")
    rendered = result[tmp_path / "out/thing.md"]
    assert "\ntimestamp:" not in rendered
    assert "internal_timestamp: '2024-01-02'" in rendered


def test_plan_okf_export_moves_timestamp_for_claim_output(tmp_path):
    project = _project(
        tmp_path,
        {"claim.md": "---\ntype: Claim\nstatus: proposed\ntimestamp: 2024-01-02\n---\n主張\n"},
    )
    result = plan_okf_export(project, tmp_path / "out")
    rendered = result[tmp_path / "out/claim.md"]
    assert "\ntimestamp:" not in rendered
    assert "internal_timestamp: '2024-01-02'" in rendered
    assert "claim_status: proposed" in rendered


def test_validate_okf_bundle_accepts_valid_bundle(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "index.md").write_text("---\nokf_version: '0.2'\n---\n# KB\n")
    (root / "thing.md").write_text(
        "---\ntype: Concept\nsources:\n  - resource: https://example.test\n"
        "status: stable\ngenerated:\n  at: 2024-01-02T03:04:05+09:00\n---\n本文\n"
    )
    assert validate_okf_bundle(root) == []


@pytest.mark.parametrize(
    "name, files, expected",
    [
        ("missing-type", {"thing.md": "---\ntitle: x\n---\n本文\n"}, "type"),
        ("bad-sources", {"thing.md": "---\ntype: Concept\nsources: nope\n---\n本文\n"}, "sources"),
        ("bad-status", {"thing.md": "---\ntype: Concept\nstatus: pending\n---\n本文\n"}, "status"),
        ("bad-time", {"thing.md": "---\ntype: Concept\ngenerated:\n  at: 2024-01-02T03:04:05\n---\n本文\n"}, "generated.at"),
        ("bad-stale-after", {"thing.md": "---\ntype: Concept\nstale_after: 2024-01-02\n---\n本文\n"}, "stale_after"),
        ("legacy-timestamp", {"thing.md": "---\ntype: Concept\ntimestamp: 2024-01-02\n---\n本文\n"}, "okf.legacy_timestamp"),
        ("sub-index-frontmatter", {"branch/index.md": "---\ntype: Index\n---\n# Branch\n"}, "index"),
    ],
)
def test_validate_okf_bundle_reports_required_violations(tmp_path, name, files, expected):
    root = tmp_path / name
    root.mkdir()
    (root / "index.md").write_text("# KB\n")
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    errors = validate_okf_bundle(root)
    assert errors
    assert expected in errors[0]


def test_validate_okf_bundle_allows_unknown_keys_and_broken_links(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "index.md").write_text("# KB\n")
    (root / "thing.md").write_text(
        "---\ntype: FutureType\nunknown: value\n---\n[missing](nowhere.md)\n"
    )
    assert validate_okf_bundle(root) == []


def test_validate_okf_bundle_accepts_okf_v02_representative_concept(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "index.md").write_text("---\nokf_version: '0.2'\n---\n# KB\n")
    (root / "concept.md").write_text(
        "---\n"
        "type: Concept\n"
        "title: 基本\n"
        "resource: https://example.test/concept\n"
        "tags: [karate, kata]\n"
        "sources:\n"
        "  - id: source-1\n"
        "    resource: https://example.test/source\n"
        "    title: Source\n"
        "    author: Author\n"
        "    usage_count: 2\n"
        "    last_modified: 2024-01-02\n"
        "usage_window: 2024\n"
        "generated:\n"
        "  at: 2024-01-02T03:04:05+09:00\n"
        "  by: importer\n"
        "verified:\n"
        "  at: 2024-01-03T03:04:05+09:00\n"
        "status: stable\n"
        "stale_after: 2025-01-02T03:04:05+09:00\n"
        "x-extension: allowed\n"
        "---\n本文\n"
    )
    assert validate_okf_bundle(root) == []


def test_validate_okf_bundle_rejects_log_frontmatter(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "index.md").write_text("# KB\n")
    (root / "log.md").write_text("---\ntitle: History\n---\n## 2024-01-01\n変更\n")
    errors = validate_okf_bundle(root)
    assert errors == ["log.md: reserved index/log documents must not have frontmatter"]


def test_render_okf_concept_rejects_missing_frontmatter():
    # Given a concept document without frontmatter.
    source = "# 拳\n"

    # When it is rendered as an OKF concept.
    with pytest.raises(OkfExportError) as raised:
        render_okf_concept("concept.md", source)

    # Then the document parse failure has a namespaced code.
    assert raised.value.code == "okf.document.invalid"


def test_render_okf_root_index_has_only_version_frontmatter():
    # Given a root index with internal metadata.
    source = "---\ntype: Index\ntitle: KB\n---\n# KB\n"

    # When it is rendered as the bundle root index.
    rendered = render_okf_index("index.md", source, root=True)

    # Then only the OKF version remains in frontmatter.
    assert rendered == "---\nokf_version: '0.2'\n---\n# KB\n"


def test_render_okf_subdirectory_index_has_no_frontmatter():
    # Given a subdirectory index with internal metadata.
    source = "---\ntype: Index\ntitle: Branch\n---\n# Branch\n"

    # When it is rendered as a subdirectory index.
    rendered = render_okf_index("branch/index.md", source, root=False)

    # Then frontmatter is removed and body is preserved.
    assert rendered == "# Branch\n"


def test_render_okf_subdirectory_index_without_frontmatter_is_unchanged():
    # Given a subdirectory index that already has no frontmatter.
    source = "# Branch\n\n本文\n"

    # When it is rendered as a subdirectory index.
    rendered = render_okf_index("branch/index.md", source, root=False)

    # Then the body remains byte-for-byte unchanged.
    assert rendered == source


def test_render_okf_wraps_yaml_serialization_failures(monkeypatch):
    # Given a serializer that fails unexpectedly.
    def fail_dump(*args, **kwargs):
        raise RuntimeError("serializer unavailable")

    monkeypatch.setattr(okf.yaml, "safe_dump", fail_dump)
    source = "---\ntype: Concept\ntitle: 拳\n---\n本文\n"

    # When the concept is rendered.
    with pytest.raises(OkfExportError) as raised:
        render_okf_concept("concept.md", source)

    # Then the failure is exposed as a stable domain error.
    assert raised.value.code == "okf.yaml.serialize"
