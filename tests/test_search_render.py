import importlib.util
import json
import sys
from pathlib import Path
from kb_harness.references import reference_spec_from_search

ROOT = Path(__file__).resolve().parents[3]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ndl_render_json_is_reference_spec_input():
    mod = load_script("ndl_search")
    results = [{"title": "Book", "authors": ["Author"], "year": "1950", "url": "https://ndl.example/1", "publisher": "Pub"}]
    payload = mod.render_results(results, "json")
    assert json.loads(payload)["results"][0]["type"] == "book"
    assert "type" not in results[0]


def test_cinii_render_json_is_reference_spec_input():
    mod = load_script("cinii_search")
    payload = mod.render_results([{"title": "Paper", "authors": ["Author"], "year": "1950", "url": "https://ci.nii.ac.jp/1", "venue": "Journal"}], "json")
    assert json.loads(payload)["results"][0]["type"] == "journal-article"


def test_provider_type_cannot_be_overridden_by_input():
    ndl = load_script("ndl_search")
    cinii = load_script("cinii_search")
    item = {"title": "x", "authors": [], "year": "", "url": "", "publisher": "", "venue": "", "type": "wrong"}
    assert json.loads(ndl.render_results([item], "json"))["results"][0]["type"] == "book"
    assert json.loads(cinii.render_results([item], "json"))["results"][0]["type"] == "journal-article"
    assert item["type"] == "wrong"


def test_reference_spec_accepts_search_script_json(tmp_path):
    mod = load_script("ndl_search")
    source = tmp_path / "search.json"
    source.write_text(mod.render_results([{"title": "Book", "authors": ["Author"], "year": "1950", "url": "https://ndl.example/1"}], "json"), encoding="utf-8")
    spec = reference_spec_from_search(source)
    assert spec["title"] == "Book"
    assert spec["type"] == "book"


def test_ndl_main_json_can_feed_reference_spec(tmp_path, monkeypatch):
    mod = load_script("ndl_search")
    monkeypatch.setattr(mod, "search", lambda *args: [{"title": "Book", "authors": ["Author"], "year": "1950", "url": "https://ndl.example/1", "publisher": ""}])
    monkeypatch.setattr(sys, "argv", ["ndl_search", "query", "--format", "json"])
    monkeypatch.setattr("sys.stdout", open(tmp_path / "out.json", "w", encoding="utf-8"))
    assert mod.main() == 0
    sys.stdout.close()
    assert reference_spec_from_search(tmp_path / "out.json")["type"] == "book"


def test_cinii_main_json_can_feed_reference_spec(tmp_path, monkeypatch):
    mod = load_script("cinii_search")
    monkeypatch.setattr(mod, "search", lambda *args: [{"title": "Paper", "authors": ["Author"], "year": "1950", "url": "https://ci.nii.ac.jp/1", "venue": ""}])
    monkeypatch.setenv("CINII_APP_ID", "test")
    monkeypatch.setattr(sys, "argv", ["cinii_search", "query", "--format", "json"])
    out = open(tmp_path / "out.json", "w", encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", out)
    assert mod.main() == 0
    out.close()
    assert reference_spec_from_search(tmp_path / "out.json")["type"] == "journal-article"


def test_yaml_render_remains_human_compatible():
    mod = load_script("ndl_search")
    text = mod.render_results([{"title": "Book", "authors": ["Author"], "year": "1950", "url": "", "publisher": "Pub"}])
    assert "type: book" in text and "title: Book" in text
