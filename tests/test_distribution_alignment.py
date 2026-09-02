from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
from types import SimpleNamespace

from kb_harness.doctor import diagnose
from kb_harness.project import Project
from kb_harness.index import plan_index
from kb_harness.graph import plan_graph

def test_distributed_ontology_dependency_provides_transition_api():
    """The published harness pin must contain the API used by claim transition."""
    harness_pyproject = (
        Path(__file__).parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    ontology_pyproject = (
        Path(__file__).parents[2] / "kb-ontology-core" / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert "kb-ontology-core @ git+ssh://git@github.com/lostandfound/kb-ontology-core.git@v0.2.0" in harness_pyproject
    assert re.search(r'version = "0\.2\.0"', ontology_pyproject)
    ontology_api = (
        Path(__file__).parents[2]
        / "kb-ontology-core"
        / "src"
        / "kb_ontology_core"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "plan_transition" in ontology_api


def test_local_wheels_expose_transition_api(tmp_path):
    """Build and install both distributions, then exercise their public imports."""
    root = Path(__file__).parents[2]
    ontology = root / "kb-ontology-core"
    target = tmp_path / "site"
    target.mkdir()
    ontology_copy = tmp_path / "kb-ontology-core"
    harness_copy = tmp_path / "kb-harness-core"
    shutil.copytree(ontology, ontology_copy, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.egg-info"))
    shutil.copytree(root / "kb-harness-core", harness_copy, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.egg-info", "build"))
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-build-isolation", "--no-deps", "--target", str(target), str(ontology_copy), str(harness_copy)],
        check=True,
        capture_output=True,
        text=True,
    )
    probe = "from kb_ontology_core import plan_transition; from kb_harness.claim import plan_claim_transition; assert plan_transition('proposed', 'accepted') == []"
    subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        cwd=tmp_path,
        env={"PYTHONPATH": str(target)},
    )


def _doctor_project(tmp_path):
    content = tmp_path / "knowledge"
    content.mkdir()
    (content / "notes").mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\n  content_root: knowledge\n", encoding="utf-8"
    )
    (content / "vocabulary.yml").write_text(
        "types:\n  Note:\n    directory: notes\n    graph: false\n"
        "predicates: {}\ntags: []\n",
        encoding="utf-8",
    )
    for path, text in plan_index(content).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(plan_graph(content, graph_path)[graph_path], encoding="utf-8")
    return Project.from_config(tmp_path / "kb-domain.yml")


def test_doctor_checks_installed_core_api_and_declared_tag(tmp_path, monkeypatch):
    """Given compatible metadata and API, doctor returns no compatibility errors."""
    import kb_harness.doctor as doctor

    project = _doctor_project(tmp_path)
    core = SimpleNamespace(
        Diagnostic=type("Diagnostic", (), {}),
        Ontology=type("Ontology", (), {}),
        export_claim=lambda *args: {},
        validate_claim=lambda *args: [],
        plan_transition=lambda *args: [],
    )
    monkeypatch.setattr(doctor.importlib, "import_module", lambda name: core)
    monkeypatch.setattr(
        doctor.importlib.metadata,
        "version",
        lambda name: {"kb-ontology-core": "0.2.0", "kb-harness-core": "0.2.0"}[name],
    )
    monkeypatch.setattr(
        doctor.importlib.metadata,
        "requires",
        lambda name: [
            "kb-ontology-core @ git+ssh://git@github.com/lostandfound/kb-ontology-core.git@v0.2.0"
        ],
    )

    details, diagnostics = diagnose(project)

    assert details["kb_ontology_core_version"] == "0.2.0"
    assert diagnostics == []


def test_doctor_reports_missing_core_api_as_structured_incompatibility(tmp_path, monkeypatch):
    """Given an installed core missing plan_transition, doctor reports incompatibility."""
    import kb_harness.doctor as doctor

    project = _doctor_project(tmp_path)
    core = SimpleNamespace(Diagnostic=type("Diagnostic", (), {}))
    monkeypatch.setattr(doctor.importlib, "import_module", lambda name: core)
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda name: "0.2.0")
    monkeypatch.setattr(
        doctor.importlib.metadata,
        "requires",
        lambda name: [
            "kb-ontology-core @ git+ssh://git@github.com/lostandfound/kb-ontology-core.git@v0.2.0"
        ],
    )

    _details, diagnostics = diagnose(project)

    assert diagnostics
    assert all(item["code"] == "doctor.ontology.api_missing" for item in diagnostics)
    assert any(item["field"] == "plan_transition" for item in diagnostics)


def test_doctor_reports_installed_core_version_mismatch(tmp_path, monkeypatch):
    """Given a tag for another version, doctor reports a version mismatch."""
    import kb_harness.doctor as doctor

    project = _doctor_project(tmp_path)
    core = SimpleNamespace(
        Diagnostic=type("Diagnostic", (), {}),
        Ontology=type("Ontology", (), {}),
        export_claim=lambda *args: {},
        validate_claim=lambda *args: [],
        plan_transition=lambda *args: [],
    )
    monkeypatch.setattr(doctor.importlib, "import_module", lambda name: core)
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda name: "0.3.0")
    monkeypatch.setattr(
        doctor.importlib.metadata,
        "requires",
        lambda name: [
            "kb-ontology-core @ git+ssh://git@github.com/lostandfound/kb-ontology-core.git@v0.2.0"
        ],
    )

    _details, diagnostics = diagnose(project)

    mismatch = next(item for item in diagnostics if item["code"] == "doctor.ontology.version_mismatch")
    assert mismatch["context"] == {"declared": "0.2.0", "installed": "0.3.0"}


def test_doctor_reports_core_import_failure(tmp_path, monkeypatch):
    """Given core metadata but an unavailable module, doctor reports import failure."""
    import kb_harness.doctor as doctor

    project = _doctor_project(tmp_path)

    def fail_import(name):
        raise ModuleNotFoundError("no module named kb_ontology_core", name="kb_ontology_core")

    monkeypatch.setattr(doctor.importlib, "import_module", fail_import)
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda name: "0.2.0")
    monkeypatch.setattr(
        doctor.importlib.metadata,
        "requires",
        lambda name: [
            "kb-ontology-core @ git+ssh://git@github.com/lostandfound/kb-ontology-core.git@v0.2.0"
        ],
    )

    _details, diagnostics = diagnose(project)

    assert diagnostics[0]["code"] == "doctor.ontology.import_failed"


def test_doctor_parses_ssh_dependency_tag(tmp_path, monkeypatch):
    """Given an SSH direct reference, doctor compares its tag to metadata."""
    import kb_harness.doctor as doctor

    project = _doctor_project(tmp_path)
    core = SimpleNamespace(
        Diagnostic=type("Diagnostic", (), {}),
        Ontology=type("Ontology", (), {}),
        export_claim=lambda *args: {},
        validate_claim=lambda *args: [],
        plan_transition=lambda *args: [],
    )
    monkeypatch.setattr(doctor.importlib, "import_module", lambda name: core)
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda name: "0.3.0")
    monkeypatch.setattr(
        doctor.importlib.metadata,
        "requires",
        lambda name: [
            "kb-ontology-core @ git+ssh://git@github.com/lostandfound/kb-ontology-core.git@v0.2.0"
        ],
    )

    _details, diagnostics = diagnose(project)

    mismatch = next(item for item in diagnostics if item["code"] == "doctor.ontology.version_mismatch")
    assert mismatch["context"]["declared"] == "0.2.0"


def test_installed_wheels_run_every_cli_family_from_isolated_directory(tmp_path):
    """Build both wheels, then exercise each top-level CLI family outside source."""
    root = Path(__file__).parents[2]
    wheel_dir = tmp_path / "wheels"
    target = tmp_path / "site"
    project = tmp_path / "fixture"
    isolated = tmp_path / "isolated"
    wheel_dir.mkdir()
    target.mkdir()
    project.mkdir()
    isolated.mkdir()

    ontology_copy = tmp_path / "kb-ontology-core"
    harness_copy = tmp_path / "kb-harness-core"
    shutil.copytree(
        root / "kb-ontology-core",
        ontology_copy,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.egg-info"),
    )
    shutil.copytree(
        root / "kb-harness-core",
        harness_copy,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.egg-info", "build", "dist"
        ),
    )
    for source in (ontology_copy, harness_copy):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                str(wheel_dir),
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    wheels = sorted(str(path) for path in wheel_dir.glob("*.whl"))
    assert len(wheels) == 2
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(target),
            *wheels,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    content = project / "knowledge"
    (content / "notes").mkdir(parents=True)
    (project / "kb-domain.yml").write_text(
        "domain:\n  content_root: knowledge\n", encoding="utf-8"
    )
    (content / "vocabulary.yml").write_text(
        "types:\n  Note:\n    directory: notes\n    graph: false\n"
        "predicates: {}\ntags: []\n",
        encoding="utf-8",
    )
    (content / "references.yml").write_text("{}\n", encoding="utf-8")
    (project / "evals").mkdir()
    (project / "evals" / "rag-eval.yml").write_text("entries: []\n", encoding="utf-8")
    spec = project / "entity.yml"
    spec.write_text(
        "type: Note\nslug: sample\ntitle: Sample\ndescription: A sample.\n"
        "tags: []\nsources: []\nsections:\n  Overview: Body\n",
        encoding="utf-8",
    )

    env = {"PATH": str(target / "bin"), "PYTHONPATH": str(target)}
    cli = [str(target / "bin" / "kb")] if (target / "bin" / "kb").is_file() else [sys.executable, "-m", "kb_harness.cli"]
    commands = (
        ["project", "show"],
        ["validate"],
        ["index", "check"],
        ["graph", "check"],
        ["sync", "--check"],
        ["entity", "create", "--from", str(spec), "--dry-run"],
        ["claim", "list"],
        ["reference", "health"],
        ["eval", "summary"],
        ["doctor"],
    )
    for command in commands:
        result = subprocess.run(
            [*cli, *command, "--start", str(project), "--format", "json"],
            cwd=isolated,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode in {0, 1}, (command, result.stdout, result.stderr)
        payload = result.stdout or result.stderr
        assert payload, command
        assert "ModuleNotFoundError" not in payload, (command, payload)
        parsed = json.loads(payload)
        assert "diagnostics" in parsed or command[0] == "project", (command, parsed)
