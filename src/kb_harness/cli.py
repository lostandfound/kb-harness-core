"""Command-line entry point for :mod:`kb_harness`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .doctor import diagnose
from .entity import EntitySpecError, plan_entity_create
from .claim import ClaimSpecError, plan_claim_create, plan_claim_transition, inspect_claim, list_claims, validate_claim_file
from .references import reference_health
from .graph import plan_graph
from .index import plan_index
from .project import Project, ProjectError
from .sync import apply_changes_atomically, plan_sync
from .validation import validate

Result = dict[str, Any]


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb")
    subcommands = parser.add_subparsers(dest="command", required=True)

    project = subcommands.add_parser("project", help="inspect KB project settings")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    show = project_commands.add_parser("show", help="show resolved project paths")
    _add_common_options(show)

    validate_parser = subcommands.add_parser("validate", help="validate the KB")
    _add_common_options(validate_parser)

    index_parser = subcommands.add_parser("index", help="build or check indexes")
    index_commands = index_parser.add_subparsers(dest="index_command", required=True)
    for command in ("build", "check"):
        command_parser = index_commands.add_parser(command)
        _add_common_options(command_parser)

    graph_parser = subcommands.add_parser("graph", help="build or check graph.json")
    graph_commands = graph_parser.add_subparsers(dest="graph_command", required=True)
    for command in ("build", "check"):
        command_parser = graph_commands.add_parser(command)
        _add_common_options(command_parser)

    sync_parser = subcommands.add_parser("sync", help="synchronize derived files")
    sync_parser.add_argument("--check", action="store_true")
    _add_common_options(sync_parser)

    entity_parser = subcommands.add_parser("entity", help="manage entities")
    entity_commands = entity_parser.add_subparsers(dest="entity_command", required=True)
    create_parser = entity_commands.add_parser("create", help="create an entity from a YAML spec")
    create_parser.add_argument("--from", dest="spec", required=True)
    create_parser.add_argument("--dry-run", action="store_true")
    create_parser.add_argument("--timestamp", default=None)
    create_parser.add_argument("--start", default=None)
    create_parser.add_argument("--format", choices=("text", "json"), default="text")
    claim_parser = subcommands.add_parser("claim", help="manage claims")
    claim_commands = claim_parser.add_subparsers(dest="claim_command", required=True)
    cc = claim_commands.add_parser("create", help="create a claim from YAML spec")
    cc.add_argument("--from", dest="spec", required=True); cc.add_argument("--dry-run", action="store_true")
    cc.add_argument("--start", default=None); cc.add_argument("--format", choices=("text", "json"), default="text")
    ci = claim_commands.add_parser("inspect"); ci.add_argument("path"); ci.add_argument("--start", default=None); ci.add_argument("--format", choices=("text", "json"), default="text")
    cl = claim_commands.add_parser("list"); cl.add_argument("--status", default=None); cl.add_argument("--start", default=None); cl.add_argument("--format", choices=("text", "json"), default="text")
    cv = claim_commands.add_parser("validate"); cv.add_argument("path"); cv.add_argument("--start", default=None); cv.add_argument("--format", choices=("text", "json"), default="text")
    ct = claim_commands.add_parser("transition"); ct.add_argument("path"); ct.add_argument("--to", dest="status"); ct.add_argument("--status", dest="legacy_status"); ct.add_argument("--start", default=None); ct.add_argument("--format", choices=("text", "json"), default="text")

    doctor_parser = subcommands.add_parser("doctor", help="check project health")
    _add_common_options(doctor_parser)
    reference = subcommands.add_parser("reference", help="manage references")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    _add_common_options(reference_commands.add_parser("health"))
    evaluation = subcommands.add_parser("eval", help="inspect evaluation assets")
    evaluation_commands = evaluation.add_subparsers(dest="eval_command", required=True)
    for name in ("summary", "smoke"):
        _add_common_options(evaluation_commands.add_parser(name))
    return parser


def _emit(result: Result, output_format: str, *, error: bool = False) -> None:
    """Render one command result with stable JSON and human text output."""
    stream = sys.stderr if error else sys.stdout
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=stream)
        return
    details = result.get("details")
    if isinstance(details, dict):
        for key, value in details.items():
            print(f"{key}: {value}", file=stream)
    diagnostics = result.get("diagnostics", [])
    if result.get("changed"):
        for path in result["changed"]:
            print(f"updated: {path}", file=stream)
    if result.get("diff") and output_format != "json":
        print(result["diff"], end="", file=stream)
    elif result.get("ok") and not diagnostics and not details:
        print("OK", file=stream)
    for diagnostic in diagnostics:
        print(diagnostic.get("message", diagnostic), file=sys.stderr)


def _project_error(error: ProjectError, output_format: str) -> int:
    _emit(
        {
            "ok": False,
            "changed": [],
            "diagnostics": [{"code": error.code, "message": str(error)}],
        },
        output_format,
        error=True,
    )
    return 2


def _internal_error(error: Exception, output_format: str) -> int:
    result = {
        "ok": False,
        "changed": [],
        "diagnostics": [
            {"code": "internal.error", "message": f"{type(error).__name__}: {error}"}
        ],
    }
    _emit(result, output_format, error=output_format != "json")
    return 3


def _relative_paths(project: Project, changes: Mapping[Path, str]) -> list[str]:
    return [str(path.relative_to(project.repo_root)) for path in changes]


def _run_derived(
    project: Project,
    *,
    check: bool,
    output_format: str,
    planner: Callable[[], Mapping[Path, str]],
    stale_code: Callable[[str], str],
    stale_message: Callable[[str], str],
) -> int:
    """Plan, check, or atomically apply generated-file changes."""
    try:
        changes = planner()
        relative_paths = _relative_paths(project, changes)
        if check:
            diagnostics = [
                {
                    "code": stale_code(path),
                    "message": stale_message(path),
                    "path": path,
                }
                for path in relative_paths
            ]
            _emit(
                {"ok": not changes, "changed": [], "diagnostics": diagnostics},
                output_format,
            )
            return 1 if changes else 0
        apply_changes_atomically(changes)
        _emit({"ok": True, "changed": relative_paths, "diagnostics": []}, output_format)
        return 0
    except Exception as error:
        return _internal_error(error, output_format)


def _validate(project: Project, output_format: str) -> int:
    try:
        errors = validate(project.content_root)
    except Exception as error:
        return _internal_error(error, output_format)
    diagnostics = [{"code": "validation.error", "message": error} for error in errors]
    _emit({"ok": not errors, "changed": [], "diagnostics": diagnostics}, output_format)
    return 1 if errors else 0


def _entity_create(project: Project, args: Any) -> int:
    try:
        plan = plan_entity_create(project, Path(args.spec), timestamp=args.timestamp)
    except EntitySpecError as error:
        _emit(
            {
                "ok": False,
                "changed": [],
                "diagnostics": [{"code": error.code, "message": str(error)}],
            },
            args.format,
            error=True,
        )
        return 2 if error.argument else 1
    except Exception as error:
        return _internal_error(error, args.format)

    relative = _relative_paths(project, plan.changes)
    result = {"ok": True, "changed": relative, "diagnostics": [], "diff": plan.diff}
    if args.dry_run:
        result["dry_run"] = True
        _emit(result, args.format)
        return 0
    try:
        apply_changes_atomically(plan.changes)
    except Exception as error:
        return _internal_error(error, args.format)
    _emit(result, args.format)
    return 0

def _claim_create(project: Project, args: Any) -> int:
    try: plan = plan_claim_create(project, Path(args.spec))
    except ClaimSpecError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True); return 2
    except OSError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": "claim.path.not_found", "message": str(error)}]}, args.format, error=True); return 2
    result = {"ok": True, "changed": _relative_paths(project, dict(plan.changes)), "diagnostics": []}
    if args.dry_run: result["dry_run"] = True; result["diff"] = ""; _emit(result, args.format); return 0
    apply_changes_atomically(dict(plan.changes)); _emit(result, args.format); return 0

def _claim_action(project: Project, args: Any) -> int:
    if args.claim_command == "list":
        claims = list_claims(project.content_root, args.status)
        _emit({"ok": True, "claims": claims, "diagnostics": []}, args.format)
        return 0
    path = Path(args.path)
    if not path.is_absolute(): path = project.content_root / path
    try:
        if args.claim_command == "inspect": _emit(inspect_claim(path), args.format); return 0
        if args.claim_command == "validate":
            errors = validate_claim_file(path)
            _emit({"ok": not errors, "changed": [], "diagnostics": [{"code": "validation.error", "message": e} for e in errors]}, args.format, error=bool(errors))
            return 1 if errors else 0
        status = args.status or args.legacy_status
        if not status: raise ClaimSpecError("transition requires --to", "claim.transition.argument")
        plan = plan_claim_transition(path, status)
        apply_changes_atomically(dict(plan.changes)); _emit({"ok": True, "changed": _relative_paths(project, dict(plan.changes)), "diagnostics": []}, args.format); return 0
    except ClaimSpecError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True); return 2
    except OSError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": "claim.path.not_found", "message": str(error)}]}, args.format, error=True); return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "project" and args.project_command == "show":
        try:
            project = Project.discover(args.start)
        except ProjectError as error:
            return _project_error(error, args.format)
        except Exception as error:
            return _internal_error(error, args.format)
        result = {
            "content_root": str(project.content_root),
            "repo_root": str(project.repo_root),
        }
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print(f"repo_root: {result['repo_root']}")
            print(f"content_root: {result['content_root']}")
        return 0

    try:
        project = Project.discover(args.start)
    except ProjectError as error:
        return _project_error(error, args.format)
    except Exception as error:
        return _internal_error(error, args.format)

    if args.command == "reference":
        result = reference_health(project.content_root / "references.yml")
        _emit(result, args.format, error=not result["ok"])
        return 0 if result["ok"] else 1
    if args.command == "eval":
        roots = [project.repo_root / "evals", project.repo_root / "eval", project.repo_root / "evaluations", project.content_root / "eval"]
        assets = sorted(str(p.relative_to(project.repo_root)) for root in roots if root.is_dir() for p in root.rglob("*") if p.is_file())
        result = {"ok": bool(assets), "assets": assets, "diagnostics": [] if assets else [{"code": "eval.assets.missing", "message": "no local evaluation assets found"}]}
        _emit(result, args.format, error=not result["ok"])
        return 0 if result["ok"] else 1
    if args.command == "validate":
        return _validate(project, args.format)

    if args.command == "entity" and args.entity_command == "create":
        return _entity_create(project, args)
    if args.command == "claim":
        return _claim_create(project, args) if args.claim_command == "create" else _claim_action(project, args)

    if args.command == "doctor":
        try:
            details, diagnostics = diagnose(project)
        except Exception as error:
            return _internal_error(error, args.format)
        _emit(
            {
                "ok": not diagnostics,
                "changed": [],
                "diagnostics": diagnostics,
                "details": details,
            },
            args.format,
        )
        return 1 if diagnostics else 0

    if args.command == "index":
        return _run_derived(
            project,
            check=args.index_command == "check",
            output_format=args.format,
            planner=lambda: plan_index(project.content_root),
            stale_code=lambda _path: "index.stale",
            stale_message=lambda path: f"index is stale: {path}",
        )

    if args.command == "graph":
        return _run_derived(
            project,
            check=args.graph_command == "check",
            output_format=args.format,
            planner=lambda: plan_graph(
                project.content_root, project.repo_root / "graph.json"
            ),
            stale_code=lambda _path: "graph.stale",
            stale_message=lambda path: f"graph is stale: {path}",
        )

    if args.command == "sync":
        return _run_derived(
            project,
            check=args.check,
            output_format=args.format,
            planner=lambda: plan_sync(project),
            stale_code=lambda path: "graph.stale" if path == "graph.json" else "index.stale",
            stale_message=lambda path: f"generated file is stale: {path}",
        )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
