"""Command-line entry point for :mod:`kb_harness`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from .concerns import (
    STATUSES as CONCERN_STATUSES,
    ConcernError,
    concern_record,
    legacy_ledger_warnings,
    load_concerns,
    select_concerns,
    summarize as summarize_concerns,
    validate_concerns,
)
from .diagnostics import HarnessError
from .doctor import diagnose
from .evaluation import smoke_result, summary_result
from .sync import unified_diff
from .entity import EntitySpecError, plan_entity_create
from .claim import ClaimSpecError, plan_claim_create, plan_claim_transition, inspect_claim, list_claims, validate_claim_file
from .references import (
    ReferencePlan,
    ReferenceSpecError,
    format_reference_block,
    format_reference_line,
    plan_reference_create,
    reference_health,
    reference_search,
    reference_show,
    reference_show_for_entity,
    reference_spec_from_search,
)
from .graph import plan_graph
from .index import plan_index
from .links import plan_link_migration
from .okf import OkfExportError, audit_okf_bundle, okf_link_warnings, plan_okf_export
from .project import Project, ProjectError
from .serve import serve
from .sync import (
    apply_changes_atomically,
    execute_write_plan,
    plan_sync,
    plan_write,
)
from .validation import check_urls, run_extra_checks, validate, warning_record
from .views import (
    ViewError,
    load_entities as _load_view_entities,
    load_views,
    query_excluded_types,
    query_predicate_matches,
    resolve_view,
    validate_views,
)

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
    validate_parser.add_argument("--check-urls", action="store_true", help="also check that source URLs are reachable")
    validate_parser.add_argument("--for", dest="url_entities", action="append", default=None, metavar="ENTITY", help="with --check-urls, check only the sources of this entity file (repeatable)")
    validate_parser.add_argument("--ref", dest="url_refs", action="append", default=None, metavar="ID", help="with --check-urls, check only this reference id (repeatable)")
    _add_common_options(validate_parser)

    okf = subcommands.add_parser("okf", help="inspect OKF bundles")
    okf_commands = okf.add_subparsers(dest="okf_command", required=True)
    okf_validate = okf_commands.add_parser("validate", help="validate an OKF v0.2 bundle")
    okf_validate.add_argument("path")
    okf_validate.add_argument("--strict", action="store_true")
    _add_common_options(okf_validate)

    export_parser = subcommands.add_parser("export", help="export KB artifacts")
    export_commands = export_parser.add_subparsers(dest="export_command", required=True)
    okf_parser = export_commands.add_parser("okf", help="export an OKF v0.2 bundle")
    okf_parser.add_argument("--output", required=True)
    okf_parser.add_argument("--dry-run", action="store_true")
    _add_common_options(okf_parser)

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

    link_parser = subcommands.add_parser("link", help="maintain body links")
    link_commands = link_parser.add_subparsers(dest="link_command", required=True)
    migrate_parser = link_commands.add_parser("migrate", help="rewrite root-relative body links as relative links")
    migrate_parser.add_argument("--check", action="store_true")
    migrate_parser.add_argument("--dry-run", action="store_true")
    _add_common_options(migrate_parser)

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
    _configure_claim_commands(claim_parser)
    view_parser = subcommands.add_parser("view", help="inspect views defined outside entities")
    view_commands = view_parser.add_subparsers(dest="view_command", required=True)
    _add_common_options(view_commands.add_parser("list", help="list views with resolved member counts"))
    resolve_parser = view_commands.add_parser("resolve", help="resolve one view to its members")
    resolve_parser.add_argument("view_id")
    _add_common_options(resolve_parser)
    _add_common_options(view_commands.add_parser("validate", help="validate view definitions"))
    concern_parser = subcommands.add_parser("concern", help="inspect the concern ledger (source and content concerns)")
    concern_commands = concern_parser.add_subparsers(dest="concern_command", required=True)
    concern_list = concern_commands.add_parser("list", help="list concerns, optionally filtered")
    concern_list.add_argument("--for", dest="target", default=None, metavar="TARGET", help="only concerns about this entity (/dir/file.md or a file path) or reference (ref: <id>)")
    concern_list.add_argument("--status", default=None, choices=CONCERN_STATUSES)
    concern_list.add_argument("--actionable", action="store_true", help="only concerns that can be worked on now (open / investigating)")
    _add_common_options(concern_list)
    _add_common_options(concern_commands.add_parser("summary", help="count concerns by status and kind"))
    _add_common_options(concern_commands.add_parser("validate", help="validate concern definitions"))

    doctor_parser = subcommands.add_parser("doctor", help="check project health")
    _add_common_options(doctor_parser)
    serve_parser = subcommands.add_parser("serve", help="view knowledge graph")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--open", action="store_true", dest="open_browser")
    _add_common_options(serve_parser)

    flashcards_parser = subcommands.add_parser("flashcards", help="study the KB with flashcards")
    flashcards_parser.add_argument("--port", type=int, default=8000)
    flashcards_parser.add_argument("--open", action="store_true", dest="open_browser")
    _add_common_options(flashcards_parser)
    reference = subcommands.add_parser("reference", help="manage references")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    _add_common_options(reference_commands.add_parser("health"))
    rc = reference_commands.add_parser("create", help="create a reference from YAML spec")
    rc.add_argument("--from", dest="spec", required=True)
    rc.add_argument("--dry-run", action="store_true")
    _add_common_options(rc)
    rshow = reference_commands.add_parser("show", help="show reference entries by id or for one entity")
    rshow.add_argument("ids", nargs="*", metavar="ID")
    rshow.add_argument("--for", dest="entity", default=None, metavar="ENTITY", help="entity file whose sources and inline citations are shown")
    _add_common_options(rshow)
    rsearch = reference_commands.add_parser("search", help="search references by terms, url or doi")
    rsearch.add_argument("terms", nargs="*", metavar="TERM")
    rsearch.add_argument("--field", action="append", dest="fields", choices=("id", "title", "author", "publisher", "journal", "url", "doi", "note", "lineage"), default=None)
    rsearch.add_argument("--url", default=None)
    rsearch.add_argument("--doi", default=None)
    rsearch.add_argument("--limit", type=int, default=None)
    rsearch.add_argument("--full", action="store_true", help="print full entries instead of one line per hit")
    _add_common_options(rsearch)
    rs = reference_commands.add_parser("spec", help="convert search output to a reference spec")
    rs.add_argument("--from", dest="source", required=True)
    rs.add_argument("--output", required=True)
    rs.add_argument("--dry-run", action="store_true")
    rs.add_argument("--force", action="store_true")
    rs.add_argument("--start", default=None)
    rs.add_argument("--format", choices=("text", "json"), default="text")
    evaluation = subcommands.add_parser("eval", help="inspect evaluation assets")
    evaluation_commands = evaluation.add_subparsers(dest="eval_command", required=True)
    _add_common_options(evaluation_commands.add_parser("summary", help="summarize evals/rag-eval.yml and detect regressions"))
    smoke = evaluation_commands.add_parser("smoke", help="check that expected evidence ranks in lexical search")
    smoke.add_argument("--limit", type=int, default=5)
    _add_common_options(smoke)
    return parser


def _configure_claim_commands(parent: argparse.ArgumentParser) -> None:
    commands = parent.add_subparsers(dest="claim_command", required=True)
    create = commands.add_parser("create", help="create a claim from YAML spec")
    create.add_argument("--from", dest="spec", required=True)
    create.add_argument("--dry-run", action="store_true")
    _add_common_options(create)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("path")
    _add_common_options(inspect)

    listing = commands.add_parser("list")
    listing.add_argument("--status", default=None)
    _add_common_options(listing)

    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("path")
    _add_common_options(validate_parser)

    transition = commands.add_parser("transition")
    transition.add_argument("path")
    transition.add_argument("--to", dest="status")
    transition.add_argument("--status", dest="legacy_status")
    transition.add_argument("--dry-run", action="store_true")
    _add_common_options(transition)


def _emit(result: Result, output_format: str, *, error: bool = False) -> None:
    """Render one command result with stable JSON and human text output.

    ``--format json`` always writes to stdout so downstream consumers can rely
    on a single stream; ``error`` only selects the stream for ``text`` output.
    """
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=sys.stdout)
        return
    stream = sys.stderr if error else sys.stdout
    details = result.get("details")
    if isinstance(details, dict):
        for key, value in details.items():
            print(f"{key}: {value}", file=stream)
    diagnostics = result.get("diagnostics", [])
    if result.get("changed"):
        verb = "would update" if result.get("dry_run") else "updated"
        for path in result["changed"]:
            print(f"{verb}: {path}", file=stream)
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
    if isinstance(error, HarnessError):
        # 利用者が直せる失敗（例: Claim を使うのに kb-ontology-core が無い）は安定したコードで返す
        result = {"ok": False, "changed": [], "diagnostics": [error.diagnostic.to_dict()]}
        _emit(result, output_format, error=output_format != "json")
        return 1
    result = {
        "ok": False,
        "changed": [],
        "diagnostics": [
            {"code": "internal.error", "message": f"{type(error).__name__}: {error}"}
        ],
    }
    _emit(result, output_format, error=True)
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
    except (ViewError, ConcernError) as error:
        # ビュー・懸念の定義の不備は利用者が直すものなので、内部エラーではなく定義の診断として返す
        _emit(
            {"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]},
            output_format,
            error=True,
        )
        return 1
    except Exception as error:
        return _internal_error(error, output_format)


def _sync_stale_code(project: Project, path: str) -> str:
    if path == "graph.json":
        return "graph.stale"
    if project.views_index is not None:
        try:
            if path == str(project.views_index.resolve().relative_to(project.repo_root.resolve())):
                return "views.stale"
        except ValueError:
            pass
    if project.concerns_index is not None:
        try:
            if path == str(project.concerns_index.resolve().relative_to(project.repo_root.resolve())):
                return "concerns.stale"
        except ValueError:
            pass
    return "index.stale"


def _view_action(project: Project, args: Any) -> int:
    if project.views_root is None:
        _emit(
            {
                "ok": False,
                "changed": [],
                "diagnostics": [
                    {"code": "view.disabled", "message": "views are not configured (kb-domain.yml views.root)"}
                ],
            },
            args.format,
            error=True,
        )
        return 2
    try:
        if args.view_command == "validate":
            errors = validate_views(project.content_root, project.views_root)
            diagnostics = [{"code": "view.error", "message": error} for error in errors]
            _emit({"ok": not diagnostics, "changed": [], "diagnostics": diagnostics}, args.format)
            return 1 if diagnostics else 0
        entities = _load_view_entities(project.content_root)
        excluded = query_excluded_types(project.content_root)
        predicate_matches = query_predicate_matches(project.content_root)
        views = load_views(project.views_root)
        if args.view_command == "list":
            items = [
                {
                    "id": view.id,
                    "name": view.name,
                    "kind": view.kind,
                    "basis": view.basis,
                    "members": len(resolve_view(view, entities, excluded, predicate_matches)),
                }
                for view in views
            ]
            if args.format == "json":
                print(json.dumps({"ok": True, "views": items}, ensure_ascii=False, sort_keys=True))
            else:
                for item in items:
                    basis = f" basis={item['basis']}" if item["basis"] else ""
                    print(f"{item['id']}\t{item['kind']}{basis}\t{item['members']}\t{item['name']}")
            return 0
        matches = [view for view in views if view.id == args.view_id]
        if not matches:
            _emit(
                {
                    "ok": False,
                    "changed": [],
                    "diagnostics": [{"code": "view.not_found", "message": f"view not found: {args.view_id}"}],
                },
                args.format,
                error=True,
            )
            return 1
        view = matches[0]
        members = [
            {"path": member.path, "note": member.note, "title": (entities.get(member.path) or {}).get("title")}
            for member in resolve_view(view, entities, excluded, predicate_matches)
        ]
        if args.format == "json":
            print(
                json.dumps(
                    {"ok": True, "id": view.id, "name": view.name, "kind": view.kind, "basis": view.basis, "members": members},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            for member in members:
                note = f" — {member['note']}" if member["note"] else ""
                print(f"{member['path']}\t{member['title'] or ''}{note}")
        return 0
    except ViewError as error:
        _emit(
            {"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]},
            args.format,
            error=True,
        )
        return 1
    except Exception as error:
        return _internal_error(error, args.format)


def _concern_target(project: Project, raw: str) -> str:
    """--for の値を懸念の targets の表記（`/dir/file.md` か `ref: <id>`）にそろえる。"""
    if raw.startswith("ref:"):
        return f"ref: {raw[len('ref:'):].strip()}"
    path = Path(raw) if Path(raw).is_absolute() else Path.cwd() / raw
    try:
        return "/" + path.resolve().relative_to(project.content_root.resolve()).as_posix()
    except ValueError:
        pass
    # ファイルシステム上の content_root の外を指す "/dir/file.md" は、targets と同じ
    # content_root 相対の表記とみなす。消えたエンティティを指す懸念もこれで引ける
    if raw.startswith("/") and raw.endswith(".md"):
        return raw
    raise ConcernError(f"--for must name an entity inside the content root or 'ref: <id>': {raw}", "concern.arguments")


def _concern_action(project: Project, args: Any) -> int:
    if project.concerns_root is None:
        _emit(
            {
                "ok": False,
                "changed": [],
                "diagnostics": [
                    {"code": "concern.disabled", "message": "concerns are not configured (kb-domain.yml concerns.root)"}
                ],
            },
            args.format,
            error=True,
        )
        return 2
    try:
        if args.concern_command == "validate":
            errors = validate_concerns(project.content_root, project.concerns_root)
            diagnostics = [{"code": "concern.error", "message": error} for error in errors]
            _emit({"ok": not diagnostics, "changed": [], "diagnostics": diagnostics}, args.format)
            return 1 if diagnostics else 0
        concerns = load_concerns(project.concerns_root)
        if args.concern_command == "summary":
            summary = summarize_concerns(concerns)
            if args.format == "json":
                print(json.dumps({"ok": True, **summary}, ensure_ascii=False, sort_keys=True))
            else:
                print(f"total\t{summary['total']}")
                print(f"actionable\t{summary['actionable']}")
                for status, count in summary["by_status"].items():
                    print(f"status:{status}\t{count}")
                for kind, count in summary["by_kind"].items():
                    print(f"kind:{kind}\t{count}")
            return 0
        target = _concern_target(project, args.target) if args.target else None
        selected = select_concerns(concerns, target=target, status=args.status, actionable=args.actionable)
        if args.format == "json":
            print(
                json.dumps(
                    {"ok": True, "concerns": [concern_record(concern) for concern in selected]},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            for concern in selected:
                print(f"{concern.id}\t{concern.status}\t{concern.kind}\t{', '.join(concern.targets)}\t{concern.summary}")
        return 0
    except ConcernError as error:
        _emit(
            {"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]},
            args.format,
            error=True,
        )
        return 1
    except Exception as error:
        return _internal_error(error, args.format)


def _validate(
    project: Project,
    output_format: str,
    *,
    urls: bool = False,
    url_entities: list[Path] | None = None,
    url_refs: list[str] | None = None,
) -> int:
    try:
        warnings: list[str] = []
        errors = validate(project.content_root, warnings=warnings, repo_root=project.repo_root)
        if project.views_root is not None:
            errors.extend(validate_views(project.content_root, project.views_root))
        if project.concerns_root is not None:
            errors.extend(validate_concerns(project.content_root, project.concerns_root))
        warnings.extend(legacy_ledger_warnings(project.repo_root, project.concerns_root))
        if urls:
            errors += check_urls(
                project.content_root, warnings=warnings, entities=url_entities, ref_ids=url_refs
            )
        checks = run_extra_checks(project.extra_checks, project.repo_root)
    except Exception as error:
        return _internal_error(error, output_format)
    diagnostics: list[dict[str, Any]] = [
        {"code": "validation.error", "message": error} for error in errors
    ]
    for check in checks:
        if check["ok"]:
            continue
        detail = f": {check['stderr']}" if check["stderr"] else ""
        diagnostics.append(
            {
                "code": "validation.extra_check.failed",
                "message": f"ERROR extra check failed (exit {check['returncode']}): {check['command']}{detail}",
                "command": check["command"],
                "returncode": check["returncode"],
            }
        )
    result: dict[str, Any] = {
        "ok": not diagnostics,
        "changed": [],
        "diagnostics": diagnostics,
        "warnings": [warning_record(warning) for warning in warnings],
    }
    if project.extra_checks:
        result["extra_checks"] = checks
    _emit(result, output_format)
    if output_format != "json":
        for warning in warnings:
            print(str(warning), file=sys.stderr)
    return 1 if diagnostics else 0


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
    try:
        plan = plan_claim_create(project, Path(args.spec))
    except ClaimSpecError as error:
        _emit(
            {"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]},
            args.format,
            error=True,
        )
        return 2
    except OSError as error:
        _emit(
            {"ok": False, "changed": [], "diagnostics": [{"code": "claim.path.not_found", "message": str(error)}]},
            args.format,
            error=True,
        )
        return 2
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
    if not path.is_absolute():
        path = project.content_root / path
    try:
        if args.claim_command == "inspect":
            _emit(inspect_claim(path), args.format)
            return 0
        if args.claim_command == "validate":
            errors = validate_claim_file(path, project.content_root)
            _emit(
                {"ok": not errors, "changed": [], "diagnostics": [{"code": "claim.validation", "message": e} for e in errors]},
                args.format,
                error=bool(errors),
            )
            return 1 if errors else 0
        status = args.status or args.legacy_status
        if not status:
            raise ClaimSpecError("transition requires --to", "claim.transition.argument")
        plan = plan_claim_transition(path, status, project)
        return _run_write_plan(
            project,
            changes=dict(plan.changes),
            diff=plan.diff,
            output_format=args.format,
            dry_run=args.dry_run,
        )
    except ClaimSpecError as error:
        _emit(
            {"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]},
            args.format,
            error=True,
        )
        return 1 if error.code in {"claim.validation", "claim.sync"} else 2
    except OSError as error:
        _emit(
            {"ok": False, "changed": [], "diagnostics": [{"code": "claim.path.not_found", "message": str(error)}]},
            args.format,
            error=True,
        )
        return 2


def _okf_output_root(project: Project, raw_output: str) -> Path:
    """Validate an OKF destination without following a destination symlink."""
    raw = Path(raw_output).expanduser()
    output = raw if raw.is_absolute() else project.repo_root / raw
    output = output.absolute()
    root = project.repo_root.resolve()
    content = project.content_root.resolve()
    resolved = output.resolve(strict=False)
    if resolved == root or resolved == content:
        raise OkfExportError("okf.output.invalid", "output must not be the repository or content root")
    try:
        resolved.relative_to(content)
    except ValueError:
        pass
    else:
        raise OkfExportError("okf.output.invalid", "output must not be inside the content root")
    if output.is_symlink():
        raise OkfExportError("okf.output.symlink", "output must not be a symlink")
    if output.exists():
        if output.is_file():
            raise OkfExportError("okf.output.exists", "output file already exists")
        if not output.is_dir():
            raise OkfExportError("okf.output.exists", "output already exists")
        if any(output.iterdir()):
            raise OkfExportError("okf.output.nonempty", "output directory must be empty")
    return output


def _okf_export(project: Project, args: Any) -> int:
    try:
        output_root = _okf_output_root(project, args.output)
        changes = plan_okf_export(project, output_root)
        plan = plan_write(changes, display_root=output_root)
    except OkfExportError as error:
        _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True)
        return 2 if error.code.startswith("okf.output.") else 1
    except Exception as error:
        return _internal_error(error, args.format)

    relative = [str(path.relative_to(output_root)) for path in plan.changes]
    # リンク切れは bundle の適合性を損なわないので、書き出しは止めず警告にとどめる
    warnings = okf_link_warnings({path.relative_to(output_root).as_posix(): text for path, text in changes.items()})
    result: Result = {"ok": True, "changed": relative, "diagnostics": [], "warnings": warnings, "diff": plan.diff}
    if args.dry_run:
        result["dry_run"] = True
        _emit_okf_export(result, args.format)
        return 0
    try:
        execute_write_plan(plan, apply=apply_changes_atomically)
    except Exception as error:
        return _internal_error(error, args.format)
    _emit_okf_export(result, args.format)
    return 0


def _reference_lookup(project: Project, args: Any) -> int:
    """``kb reference show`` / ``kb reference search``: レジストリを丸ごと読まずに必要な項目だけ返す。"""
    registry = project.content_root / "references.yml"
    try:
        if args.reference_command == "show":
            if args.entity:
                if args.ids:
                    raise ReferenceSpecError("reference.show.arguments", "give either ids or --for, not both")
                entity = Path(args.entity)
                if not entity.is_absolute():
                    entity = Path.cwd() / entity
                result = reference_show_for_entity(registry, entity)
            elif args.ids:
                result = reference_show(registry, list(args.ids))
            else:
                raise ReferenceSpecError("reference.show.arguments", "give at least one id or --for ENTITY")
            full = True
        else:
            if not args.terms and not args.url and not args.doi:
                raise ReferenceSpecError("reference.search.arguments", "give search terms, --url or --doi")
            result = reference_search(
                registry,
                list(args.terms),
                fields=tuple(args.fields) if args.fields else None,
                url=args.url,
                doi=args.doi,
                limit=args.limit,
            )
            full = args.full
    except ReferenceSpecError as error:
        _emit({"ok": False, "entries": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True)
        return 2
    except Exception as error:
        return _internal_error(error, args.format)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=_json_date))
    else:
        for entry in result["entries"]:
            print(format_reference_block(entry) if full else format_reference_line(entry), end="" if full else "\n")
        if args.reference_command == "search":
            print(f"count: {result['count']}" + (f" (shown {result['shown']})" if result["shown"] != result["count"] else ""), file=sys.stderr)
        for diagnostic in result.get("diagnostics", []):
            print(diagnostic["message"], file=sys.stderr)
    return 0 if result["ok"] else 1


def _json_date(value: object) -> str:
    if not isinstance(value, date):
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
    return value.isoformat()


def _emit_okf_export(result: Result, output_format: str) -> None:
    _emit(result, output_format)
    if output_format != "json":
        for item in result["warnings"]:
            print(f"WARNING {item['path']}: {item['code']}: {item['message']}", file=sys.stderr)


def _okf_validate(args: Any) -> int:
    try:
        root = Path(args.path).expanduser()
        if not root.is_absolute():
            base = Path(args.start).expanduser() if args.start else Path.cwd()
            if not base.is_absolute():
                base = Path.cwd() / base
            root = base / root
        result = audit_okf_bundle(root)
    except Exception as error:
        return _internal_error(error, args.format)
    diagnostics = result["diagnostics"]
    warnings = result["warnings"]
    payload = {"ok": not diagnostics and (not args.strict or not warnings), "diagnostics": diagnostics, "warnings": warnings, "strict": args.strict}
    if args.format == "json":
        _emit(payload, args.format, error=not payload["ok"])
    else:
        if not diagnostics and not warnings:
            print("OK")
        for item in diagnostics:
            print(f"{item['path']}: {item['code']}: {item['message']}", file=sys.stderr)
        for item in warnings:
            print(f"{item['path']}: {item['code']}: {item['message']}", file=sys.stderr)
    if any(item["code"] == "okf.bundle.not_directory" for item in diagnostics):
        return 2
    return 1 if diagnostics or (args.strict and warnings) else 0


def _main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "okf" and args.okf_command == "validate":
        return _okf_validate(args)
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

    if args.command == "export" and args.export_command == "okf":
        return _okf_export(project, args)

    if args.command == "reference" and args.reference_command == "create":
        try:
            plan = plan_reference_create(project.content_root / "references.yml", Path(args.spec))
        except ReferenceSpecError as error:
            _emit({"ok": False, "changed": [], "diagnostics": [{"code": error.code, "message": str(error)}]}, args.format, error=True)
            return 2 if error.argument else 1
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
            diff = unified_diff({output: output_text})
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
    if args.command == "reference" and args.reference_command in ("show", "search"):
        return _reference_lookup(project, args)
    if args.command == "reference":
        result = reference_health(project.content_root / "references.yml")
        _emit(result, args.format, error=not result["ok"])
        return 0 if result["ok"] else 1
    if args.command == "eval":
        try:
            if args.eval_command == "smoke":
                result = smoke_result(project.repo_root, project.content_root, limit=args.limit)
            else:
                result = summary_result(project.repo_root)
        except Exception as error:
            return _internal_error(error, args.format)
        _emit(result, args.format, error=not result["ok"])
        return 0 if result["ok"] else 1
    if args.command == "validate":
        if (args.url_entities or args.url_refs) and not args.check_urls:
            _emit(
                {
                    "ok": False,
                    "errors": [],
                    "warnings": [],
                    "diagnostics": [
                        {"code": "validation.arguments", "message": "--for and --ref require --check-urls"}
                    ],
                },
                args.format,
                error=True,
            )
            return 2
        url_entities = None
        if args.url_entities:
            url_entities = [
                Path(entity) if Path(entity).is_absolute() else Path.cwd() / entity
                for entity in args.url_entities
            ]
        return _validate(
            project,
            args.format,
            urls=args.check_urls,
            url_entities=url_entities,
            url_refs=list(args.url_refs) if args.url_refs else None,
        )

    if args.command == "entity" and args.entity_command == "create":
        return _entity_create(project, args)
    if args.command == "claim":
        return _claim_create(project, args) if args.claim_command == "create" else _claim_action(project, args)
    if args.command == "view":
        return _view_action(project, args)
    if args.command == "concern":
        return _concern_action(project, args)

    if args.command == "doctor":
        try:
            details, diagnostics = diagnose(project)
        except Exception as error:
            return _internal_error(error, args.format)
        # severity: warning の診断（extra_checks のコマンド不在など）は失敗にしない
        problems = [d for d in diagnostics if d.get("severity", "error") != "warning"]
        _emit(
            {
                "ok": not problems,
                "changed": [],
                "diagnostics": diagnostics,
                "details": details,
            },
            args.format,
        )
        return 1 if problems else 0

    if args.command == "index":
        return _run_derived(
            project,
            check=args.index_command == "check",
            dry_run=args.dry_run,
            output_format=args.format,
            planner=lambda: plan_index(
                project.content_root,
                by_tag=project.index_by_tag,
                tag_labels=project.tag_labels,
            ),
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
                project.content_root, project.repo_root / "graph.json", project.views_root
            ),
            stale_code=lambda _path: "graph.stale",
            stale_message=lambda path: f"graph is stale: {path}",
        )

    if args.command == "link" and args.link_command == "migrate":
        return _run_derived(
            project,
            check=args.check,
            dry_run=args.dry_run,
            output_format=args.format,
            planner=lambda: plan_link_migration(project.content_root),
            stale_code=lambda _path: "link.root_relative",
            stale_message=lambda path: f"root-relative body links remain: {path}",
        )

    if args.command == "sync":
        return _run_derived(
            project,
            check=args.check,
            dry_run=args.dry_run,
            output_format=args.format,
            planner=lambda: plan_sync(project),
            stale_code=lambda path: _sync_stale_code(project, path),
            stale_message=lambda path: f"generated file is stale: {path}",
        )

    if args.command == "serve":
        serve(project, port=args.port, open_browser=args.open_browser)
        return 0

    if args.command == "flashcards":
        serve(project, port=args.port, open_browser=args.open_browser, view="flashcards")
        return 0

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
