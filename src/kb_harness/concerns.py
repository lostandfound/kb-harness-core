"""懸念台帳: エンティティや出典の確からしさについての注記。

懸念は `kb-domain.yml` の `concerns.root` 配下に 1 件 1 YAML で置く。1 件は必ず
実在するエンティティ（content_root 相対の `/dir/file.md`）か `ref: <id>` を対象に持つ。
結びつく先の無いもの（作業の予定、ハーネスの問題、漠然とした違和感）は書けない。
作業は導入先の BACKLOG に、型や境界の判断は review-entity-model の出力に置く。

一覧（`concerns.index`）は `kb sync` が生成する。判断の経緯は
docs/notes/kenen-daichou-memo.md。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .validation import FILENAME_RE, ValidationWarning, _load_references
from .views import load_entities


KINDS = ("conflict", "weak-source", "indirect", "unreachable", "judgment")
KIND_LABELS = {
    "conflict": "出典どうしの食い違い",
    "weak-source": "出典が弱い・単一系統",
    "indirect": "孫引き・原典と未照合",
    "unreachable": "出典を取得できない",
    "judgment": "値や系統を選んだ判断",
}
# 一覧の並びも兼ねる。着手できるもの → 動かせないもの → 終わったもの
STATUSES = ("open", "investigating", "blocked-source", "suspended", "settled-hedged", "resolved")
STATUS_LABELS = {
    "open": "未着手",
    "investigating": "調査中",
    "blocked-source": "資料待ち",
    "suspended": "打ち切り（再開条件つき）",
    "settled-hedged": "決着せず記述側は完了",
    "resolved": "解決",
}
ACTIONABLE = ("open", "investigating")
# 状態に付く欄。記述側で何をしたか・何を待つか・いつ再開するかを残させる。
# その状態では必須、ほかの状態では書けない（状態を変えたら欄も改める）
STATUS_FIELDS = {
    "resolution": ("settled-hedged", "resolved"),
    "awaiting": ("blocked-source",),
    "resume_when": ("suspended",),
}
TEXT_KEYS = ("summary", "detail", "resolution", "awaiting", "resume_when")
CONCERN_KEYS = ("targets", "kind", "status", "sources", *TEXT_KEYS)
LEGACY_LEDGER = Path("docs") / "CONCERNS.md"


@dataclass(frozen=True)
class Concern:
    id: str
    path: Path
    targets: tuple[str, ...]
    kind: str
    status: str
    summary: str
    detail: str = ""
    sources: tuple[str, ...] = ()
    resolution: str = ""
    awaiting: str = ""
    resume_when: str = ""

    @property
    def actionable(self) -> bool:
        return self.status in ACTIONABLE


class ConcernError(ValueError):
    def __init__(self, message: str, code: str = "concern.spec"):
        super().__init__(message)
        self.code = code


def ref_id(target: str) -> str | None:
    """`ref: <id>` なら id を、そうでなければ None を返す。"""
    if target.startswith("ref:"):
        return target[len("ref:"):].strip()
    return None


def _concern_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(path for path in root.glob("*.yml") if path.is_file()) + sorted(
        path for path in root.glob("*.yaml") if path.is_file()
    )


def _text(data: dict, key: str, name: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ConcernError(f"{name}: '{key}' must be a string")
    return value.strip()


def _string_list(data: dict, key: str, name: str) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConcernError(f"{name}: '{key}' must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def load_concern(path: Path) -> Concern:
    """1 件の懸念 YAML を読む。形式の不備は ConcernError。実在の照合は validate_concerns が行う。"""
    name = path.name
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConcernError(f"{name}: invalid YAML: {error}", "concern.yaml") from error
    if not isinstance(data, dict):
        raise ConcernError(f"{name}: concern must be a mapping")
    unknown = sorted(str(key) for key in set(data) - set(CONCERN_KEYS))
    if unknown:
        raise ConcernError(
            f"{name}: unknown key(s): {', '.join(unknown)}（懸念が持てる欄は {', '.join(CONCERN_KEYS)}）"
        )
    targets = _string_list(data, "targets", name)
    if not targets:
        raise ConcernError(
            f"{name}: 'targets' is required: list the entities (/dir/file.md) or references (ref: <id>) "
            "this concern is about. Work items belong in the BACKLOG, not here"
        )
    kind = data.get("kind")
    if kind not in KINDS:
        raise ConcernError(f"{name}: kind must be one of {', '.join(KINDS)}")
    status = data.get("status")
    if status not in STATUSES:
        raise ConcernError(f"{name}: status must be one of {', '.join(STATUSES)}")
    texts = {key: _text(data, key, name) for key in TEXT_KEYS}
    if not texts["summary"]:
        raise ConcernError(f"{name}: missing required field 'summary'")
    for key, statuses in STATUS_FIELDS.items():
        if status in statuses and not texts[key]:
            raise ConcernError(f"{name}: status '{status}' requires '{key}'")
        if status not in statuses and texts[key]:
            raise ConcernError(f"{name}: '{key}' is only for status {' / '.join(statuses)}")
    return Concern(
        id=path.stem,
        path=path,
        targets=targets,
        kind=kind,
        status=status,
        sources=_string_list(data, "sources", name),
        **texts,
    )


def _duplicate_ids(paths: list[Path]) -> dict[str, list[str]]:
    by_id: dict[str, list[str]] = {}
    for path in paths:
        by_id.setdefault(path.stem, []).append(path.name)
    return {concern_id: names for concern_id, names in by_id.items() if len(names) > 1}


def load_concerns(root: Path) -> list[Concern]:
    """root 配下の全懸念を id 順に返す。形式不備は最初の 1 件で ConcernError。"""
    paths = _concern_files(root)
    duplicates = _duplicate_ids(paths)
    if duplicates:
        concern_id, names = sorted(duplicates.items())[0]
        raise ConcernError(f"duplicate concern id '{concern_id}': {', '.join(names)}", "concern.duplicate")
    concerns = [load_concern(path) for path in paths]
    concerns.sort(key=lambda concern: concern.id)
    return concerns


def validate_concerns(content_root: Path, root: Path) -> list[str]:
    """懸念を実在するエンティティと出典に照らして検査する。

    戻り値は `kb validate` の errors と同じ `ERROR <相対パス>: <内容>` 形式。
    """
    errors: list[str] = []
    if not root.is_dir():
        return errors
    entities = load_entities(content_root)
    references, _ref_errors = _load_references(content_root)
    paths = _concern_files(root)
    for concern_id, names in sorted(_duplicate_ids(paths).items()):
        errors.append(f"ERROR {root.name}/{names[0]}: concern id '{concern_id}' が重複している（{', '.join(names)}）")
    for path in paths:
        rel = f"{root.name}/{path.name}"
        if not FILENAME_RE.match(path.stem + ".md"):
            errors.append(f"ERROR {rel}: ファイル名がケバブケース規約に反する '{path.name}'")
        try:
            concern = load_concern(path)
        except ConcernError as error:
            errors.append(f"ERROR {rel}: {error}")
            continue
        seen: set[str] = set()
        for target in concern.targets:
            if target in seen:
                errors.append(f"ERROR {rel}: targets の '{target}' が重複している")
            seen.add(target)
            ref = ref_id(target)
            if ref is not None:
                if ref not in references:
                    errors.append(f"ERROR {rel}: targets の 'ref: {ref}' が references.yml に存在しない")
            elif not target.startswith("/"):
                errors.append(
                    f"ERROR {rel}: targets の '{target}' は content_root 相対の '/dir/file.md' か 'ref: <id>' で書く"
                )
            elif target not in entities:
                # 一覧（index.md）はエンティティではないので、ここで存在しない扱いになる
                errors.append(f"ERROR {rel}: targets の '{target}' does not exist")
        for source in concern.sources:
            ref = ref_id(source)
            if ref is not None and ref not in references:
                errors.append(f"ERROR {rel}: sources の 'ref: {ref}' が references.yml に存在しない")
    return errors


def legacy_ledger_warnings(repo_root: Path, root: Path | None) -> list[ValidationWarning]:
    """構造化した台帳を使う KB に旧来の docs/CONCERNS.md が残っていれば WARNING。"""
    if root is None or not (repo_root / LEGACY_LEDGER).is_file():
        return []
    return [
        ValidationWarning(
            f"/{LEGACY_LEDGER.as_posix()}: concerns.root が設定されているのに旧来の懸念台帳が残っている。"
            f"各行を {root.name}/ の YAML へ移し、ファイルを消す",
            code="concern.legacy_ledger",
        )
    ]


def select_concerns(
    concerns: list[Concern],
    *,
    target: str | None = None,
    status: str | None = None,
    actionable: bool = False,
) -> list[Concern]:
    """対象・状態・着手可能で絞る。条件は AND。"""
    selected = concerns
    if target is not None:
        selected = [concern for concern in selected if target in concern.targets]
    if status is not None:
        selected = [concern for concern in selected if concern.status == status]
    if actionable:
        selected = [concern for concern in selected if concern.actionable]
    return selected


def summarize(concerns: list[Concern]) -> dict[str, Any]:
    by_status = {status: 0 for status in STATUSES}
    by_kind = {kind: 0 for kind in KINDS}
    for concern in concerns:
        by_status[concern.status] += 1
        by_kind[concern.kind] += 1
    return {
        "total": len(concerns),
        "by_status": by_status,
        "by_kind": by_kind,
        "actionable": sum(1 for concern in concerns if concern.actionable),
    }


def concern_record(concern: Concern) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": concern.id,
        "targets": list(concern.targets),
        "kind": concern.kind,
        "status": concern.status,
        "summary": concern.summary,
    }
    for key in ("detail", "resolution", "awaiting", "resume_when"):
        if getattr(concern, key):
            record[key] = getattr(concern, key)
    if concern.sources:
        record["sources"] = list(concern.sources)
    return record


INDEX_HEADING = "# 懸念一覧"
INDEX_NOTE = (
    "エンティティと出典の確からしさについての懸念。`kb sync` が生成するので手で編集しない。"
    "懸念は定義ファイル（1 件 1 YAML）を編集する。作業の予定はここではなく BACKLOG に置く。"
)


def render_concerns_index(content_root: Path, root: Path, index_path: Path | None = None) -> str:
    """懸念一覧を状態ごとに描画する。リンクは一覧ファイルからの相対パスにする。"""
    index_dir = (index_path or root / "index.md").resolve().parent
    content_dir = content_root.resolve()
    entities = load_entities(content_root)
    concerns = load_concerns(root)
    summary = summarize(concerns)
    lines = [INDEX_HEADING, "", INDEX_NOTE, ""]
    counts = "、".join(
        f"{STATUS_LABELS[status]} {summary['by_status'][status]}" for status in STATUSES if summary["by_status"][status]
    )
    lines.append(f"全 {summary['total']} 件" + (f"（{counts}）" if counts else ""))
    lines.append("")
    for status in STATUSES:
        group = [concern for concern in concerns if concern.status == status]
        if not group:
            continue
        lines.append(f"## {STATUS_LABELS[status]}（{status}）")
        lines.append("")
        for concern in group:
            links = []
            for target in concern.targets:
                ref = ref_id(target)
                if ref is not None:
                    links.append(f"`ref: {ref}`")
                    continue
                title = str((entities.get(target) or {}).get("title") or target)
                href = Path(os.path.relpath(content_dir / target.lstrip("/"), index_dir)).as_posix()
                links.append(f"[{title}]({href})")
            definition = Path(os.path.relpath(concern.path.resolve(), index_dir)).as_posix()
            lines.append(
                f"- {'、'.join(links)}: {concern.summary}（{concern.kind}、[{concern.id}]({definition})）"
            )
            for key, label in (("awaiting", "待っている資料"), ("resume_when", "再開条件"), ("resolution", "対応")):
                value = getattr(concern, key)
                if value:
                    lines.append(f"  - {label}: {' '.join(value.split())}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def plan_concerns_index(content_root: Path, root: Path | None, index_path: Path | None) -> dict[Path, str]:
    """懸念一覧の生成計画。concerns が未設定なら空。"""
    if root is None or index_path is None or not root.is_dir():
        return {}
    rendered = render_concerns_index(content_root, root, index_path)
    output = index_path.resolve()
    current = output.read_text(encoding="utf-8") if output.is_file() else None
    if current == rendered:
        return {}
    return {output: rendered}
