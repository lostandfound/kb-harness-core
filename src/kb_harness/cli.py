"""Command-line entry point for :mod:`kb_harness`."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from .doctor import diagnose
from .entity import EntitySpecError, plan_entity_create
from .claim import ClaimSpecError, plan_claim_create, plan_claim_transition, inspect_claim, list_claims, validate_claim_file
from .references import (
    ReferencePlan,
    ReferenceSpecError,
    plan_reference_create,
    reference_health,
    reference_spec_from_search,
)
from .graph import plan_graph
from .index import plan_index
from .project import Project, ProjectError
from .sync import (
    apply_changes_atomically,
    execute_write_plan,
    plan_sync,
    plan_write,
)
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
        command_parser.add_argument("--dry-run", action="store_true")
        _add_common_options(command_parser)

    graph_parser = subcommands.add_parser("graph", help="build or check graph.json")
    graph_commands = graph_parser.add_subparsers(dest="graph_command", required=True)
    for command in ("build", "check"):
        command_parser = graph_commands.add_parser(command)
        command_parser.add_argument("--dry-run", action="store_true")
        _add_common_options(command_parser)

    sync_parser = subcommands.add_parser("sync", help="synchronize derived files")
    sync_parser.add_argument("--check", action="store_true")
    sync_parser.add_argument("--dry-run", action="store_true")
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
    ct = claim_commands.add_parser("transition"); ct.add_argument("path"); ct.add_argument("--to", dest="status"); ct.add_argument("--status", dest="legacy_status"); ct.add_argument("--dry-run", action="store_true"); ct.add_argument("--start", default=None); ct.add_argument("--format", choices=("text", "json"), default="text")

    doctor_parser = subcommands.add_parser("doctor", help="check project health")
    _add_common_options(doctor_parser)
    reference = subcommands.add_parser("reference", help="manage references")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    _add_common_options(reference_commands.add_parser("health"))
    rc = reference_commands.add_parser("create", help="create a reference from YAML spec")
    rc.add_argument("--from", dest="spec", required=True)
    rc.add_argument("--dry-run", action="store_true")
    _add_common_options(rc)
    rs = reference_commands.add_parser("spec", help="convert search output to a reference spec")
    rs.add_argument("--from", dest="source", required=True)
    rs.add_argument("--output", required=True)
    rs.add_argument("--dry-run", action="store_true")
    rs.add_argument("--force", action="store_true")
    rs.add_argument("--start", default=None)
    rs.add_argument("--format", choices=("text", "json"), default="text")
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
    dry_run: bool,
    output_format: str,
    planner: Callable[[], Mapping[Path, str]],
    stale_code: Callable[[str], str],
    stale_message: Callable[[str], str],
) -> int:
    """Plan, check, or atomically apply generated-file changes."""
    try:
        changes = planner()
        relative_paths = _relative_paths(project, changes)
        plan = plan_write(changes, display_root=project.repo_root)
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
                {
                    "ok": not changes,
                    "changed": [],
                    "diagnostics": diagnostics,
                    "diff": plan.diff,
                },
                output_format,
            )
            return 1 if changes else 0
        return _run_write_plan(
            project,
            changes=plan.changes,
            diff=plan.diff,
            output_format=output_format,
            dry_run=dry_run,
        )
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

    return _run_write_plan(
        project,
        changes=plan.changes,
        diff=plan.diff,
        output_format=args.format,
        dry_run=args.dry_run,
    )


def _run_write_plan(
    project: Project,
    *,
    changes: Mapping[Path, str],
    diff: str,
    output_format: str,
    dry_run: bool,
    changed: Sequence[str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> int:
    """Render a planned write and apply it only after planning succeeds."""
    # Re-render at the CLI boundary so domain planners cannot leak absolute
    # checkout or temporary staging paths into user-facing output.
    plan = plan_write(changes, diff=diff or None, display_root=project.repo_root)
    relative = list(changed) if changed is not None else _relative_paths(project, plan.changes)
    result: Result = {
        "ok": True,
        "changed": relative,
        "diagnostics": [],
        "diff": plan.diff,
    }
    if extra:
        result.update(extra)
    if dry_run:
        result["dry_run"] = True
        _emit(result, output_format)
        return 0
    try:
        execute_write_plan(plan, apply=apply_changes_atomically)
    except Exception as error:
        return _internal_error(error, output_format)
    _emit(result, output_format)
    return 0


def _resolve_reference_output(project: Project, raw_output: str, *, force: bool) -> Path:
    """Resolve and validate a generated spec path without following it on write.

    The resolved path is used only for containment checks.  The lexical path is
    returned so an atomic replace replaces a symlink itself rather than writing
    through it.
    """
    raw_path = Path(raw_output).expanduser()
    output = raw_path if raw_path.is_absolute() else project.repo_root / raw_path
    output = output.absolute()
    root = project.repo_root.resolve()
    try:
        resolved = output.resolve(strict=False)
        resolved.relative_to(root)
    except ValueError as error:
        raise ReferenceSpecError(
            "reference.output.outside_project",
            f"output must be within project root: {raw_output}",
        ) from error

    if output.exists() or output.is_symlink():
        if output.is_dir():
            raise ReferenceSpecError(
                "reference.output.invalid", f"output is a directory: {raw_output}"
            )
        if not force:
            raise ReferenceSpecError(
                "reference.output.exists",
                f"output already exists (use --force): {raw_output}",
            )
    return output

def _claim_create(project: Project, args: Any) -> int:
    try: plan = plan_claim_create(project, Path(args.spec))
    except ClaimSpecError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True); return 2
    except OSError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": "claim.path.not_found", "message": str(error)}]}, args.format, error=True); return 2
    return _run_write_plan(
        project,
        changes=dict(plan.changes),
        diff=plan.diff,
        output_format=args.format,
        dry_run=args.dry_run,
    )

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
            errors = validate_claim_file(path, project.content_root)
            _emit({"ok": not errors, "changed": [], "diagnostics": [{"code": "claim.validation", "message": e} for e in errors]}, args.format, error=bool(errors))
            return 1 if errors else 0
        status = args.status or args.legacy_status
        if not status: raise ClaimSpecError("transition requires --to", "claim.transition.argument")
        plan = plan_claim_transition(path, status, project)
        return _run_write_plan(
            project,
            changes=dict(plan.changes),
            diff=plan.diff,
            output_format=args.format,
            dry_run=args.dry_run,
        )
    except ClaimSpecError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True); return 1 if error.code in {"claim.validation", "claim.sync"} else 2
    except OSError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": "claim.path.not_found", "message": str(error)}]}, args.format, error=True); return 2


def _main(argv: Sequence[str] | None = None) -> int:
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

    if args.command == "reference" and args.reference_command == "create":
        try:
            plan = plan_reference_create(project.content_root / "references.yml", Path(args.spec))
        except ReferenceSpecError as error:
            _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True)
            return 2
        except Exception as error:
            return _internal_error(error, args.format)
        return _run_write_plan(
            project,
            changes=plan.changes,
            diff=plan.diff,
            output_format=args.format,
            dry_run=args.dry_run,
            changed=["references.yml"],
        )
    if args.command == "reference" and args.reference_command == "spec":
        try:
            spec = reference_spec_from_search(Path(args.source))
            output = _resolve_reference_output(project, args.output, force=args.force)
            output_text = yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)
            old_text = output.read_text(encoding="utf-8") if output.is_file() else ""
            diff = "".join(
                difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    output_text.splitlines(keepends=True),
                    fromfile=f"a/{output}",
                    tofile=f"b/{output}",
                )
            )
            plan = ReferencePlan({output: output_text}, diff=diff)
        except ReferenceSpecError as error:
            _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True)
            return 2 if error.code.startswith("reference.output.") else 1
        except Exception as error:
            return _internal_error(error, args.format)
        return _run_write_plan(
            project,
            changes=plan.changes,
            diff=plan.diff,
            output_format=args.format,
            dry_run=args.dry_run,
            extra={"spec": spec},
        )
    if args.command == "reference":
        result = reference_health(project.content_root / "references.yml")
        _emit(result, args.format, error=not result["ok"])
        return 0 if result["ok"] else 1
    if args.command == "eval":
        roots = [project.repo_root / "evals", project.repo_root / "eval", project.repo_root / "evaluations", project.content_root / "eval"]
        assets = sorted(str(p.relative_to(project.repo_root)) for root in roots if root.is_dir() for p in root.rglob("*") if p.is_file())
        result = {"ok": bool(assets), "assets": assets, "diagnostics": [] if assets else [{"code": "eval.assets.missing", "message": "no local evaluation assets found"}]}
        if assets:
            path = project.repo_root / assets[0]
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            entries = data if isinstance(data, list) else data.get("entries", [])
            verdicts = Counter()
            open_gaps = []
            for entry in entries:
                history = entry.get("history", []) if isinstance(entry, dict) else []
                if not history:
                    continue
                latest = history[-1]
                verdict = str(latest.get("verdict", "")).strip()
                verdicts[verdict] += 1
                if verdict != "OK" and entry.get("gap") != "by-design":
                    open_gaps.append({"id": entry.get("id"), "kind": entry.get("kind"), "gap": entry.get("gap")})
            result["summary"] = {"evaluated": sum(verdicts.values()), "by_verdict": dict(sorted(verdicts.items()))}
            result["open_gaps"] = sorted(open_gaps, key=lambda item: str(item.get("id", "")))
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
            dry_run=args.dry_run,
            output_format=args.format,
            planner=lambda: plan_index(project.content_root),
            stale_code=lambda _path: "index.stale",
            stale_message=lambda path: f"index is stale: {path}",
        )

    if args.command == "graph":
        return _run_derived(
            project,
            check=args.graph_command == "check",
            dry_run=args.dry_run,
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
            dry_run=args.dry_run,
            output_format=args.format,
            planner=lambda: plan_sync(project),
            stale_code=lambda path: "graph.stale" if path == "graph.json" else "index.stale",
            stale_message=lambda path: f"generated file is stale: {path}",
        )

    return 2


def _requested_format(argv: Sequence[str] | None) -> str:
    values = list(argv) if argv is not None else sys.argv[1:]
    for index, value in enumerate(values[:-1]):
        if value == "--format" and values[index + 1] in {"text", "json"}:
            return values[index + 1]
    return "text"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI with one structured boundary for unexpected failures."""
    try:
        return _main(argv)
    except Exception as error:
        return _internal_error(error, _requested_format(argv))


if __name__ == "__main__":
    raise SystemExit(main())
