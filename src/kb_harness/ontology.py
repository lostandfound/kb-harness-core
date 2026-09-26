"""Bridge from the Markdown harness to the ontology domain package.

kb-ontology-core は Claim（出典と確度を伴う関係主張）を使う導入先だけが要る。
この層は読み込み時にコアを import せず、Claim の検証・出力・語彙の構築を
呼ばれた時点で解決する。Claim を使わない KB はコアなしで全機能が動く。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from .diagnostics import Diagnostic as HarnessDiagnostic, HarnessError

_CORE_NAME = "kb_ontology_core"
_core_module: Any = None


class OntologyCoreMissing(HarnessError):
    """Claim を扱おうとしたが kb-ontology-core が入っていない。"""

    def __init__(self) -> None:
        super().__init__(
            HarnessDiagnostic(
                "ontology.core.missing",
                "kb-ontology-core is required for Claim support; install it "
                "(pip install -r requirements.txt) or place it beside kb-harness-core",
            )
        )


def _try_import() -> Any:
    # テストや上位が sys.modules に None を置いて「無い」状態を作れるようにする
    if sys.modules.get(_CORE_NAME, False) is None:
        return None
    try:
        return __import__(_CORE_NAME)
    except ModuleNotFoundError as error:
        if error.name != _CORE_NAME:
            raise
        return None


def load_core() -> Any:
    """kb_ontology_core を解決して返す。pip 導入か、兄弟ディレクトリ ../kb-ontology-core/src へのフォールバック。"""
    global _core_module
    if _core_module is not None:
        return _core_module
    module = _try_import()
    if module is None:
        sibling_src = Path(__file__).resolve().parents[3] / "kb-ontology-core" / "src"
        if sibling_src.is_dir() and str(sibling_src) not in sys.path:
            sys.path.insert(0, str(sibling_src))
            module = _try_import()
    if module is None:
        raise OntologyCoreMissing()
    _core_module = module
    return module


def core_available() -> bool:
    """コアを解決できるか。テストの skip 判定と kb doctor が使う。"""
    try:
        load_core()
    except OntologyCoreMissing:
        return False
    return True


def build_ontology(mapping: Mapping[str, object]) -> Any:
    """語彙の写像からコアの Ontology を組む。Claim の検証にだけ要る。"""
    return load_core().Ontology.from_mapping(mapping)


def export_claim(path: str, frontmatter: Mapping[str, object]) -> Any:
    """Claim を graph.json 用に直列化する（コアの export_claim）。"""
    return load_core().export_claim(path, frontmatter)


def __getattr__(name: str) -> Any:
    # 互換: `ontology.Ontology` / `ontology.Diagnostic` / `ontology._core` はコアを遅延解決して返す
    if name in ("Ontology", "Diagnostic"):
        return getattr(load_core(), name)
    if name == "_core":
        return load_core()
    raise AttributeError(name)


def _translate_diagnostic(path: str, diagnostic: Any) -> str:
    """Translate a core diagnostic without inspecting its human text.

    The harness keeps its historical text return value for compatibility.  All
    branching is keyed by the core's stable code; ``field`` and ``context``
    provide the values needed to render the old Japanese/English messages.
    """
    context = diagnostic.context or {}
    field = diagnostic.field
    value = context.get("value")
    if diagnostic.code == "claim.field.missing":
        message = f"Claim missing required field '{field}'"
    elif diagnostic.code == "claim.sources.empty":
        message = "Claim sources must contain at least one entry"
    elif diagnostic.code == "claim.status.unknown":
        if value is None:
            message = f"Claim {diagnostic}"
        else:
            message = f"Claim status '{value}' は許容値でない"
    elif diagnostic.code == "claim.confidence.unknown":
        message = f"Claim confidence '{value}' は A/B/C/D のいずれか"
    elif diagnostic.code in {"claim.subject.not_found", "claim.object.not_found"}:
        message = f"Claim {field} '{value}' does not exist"
    elif diagnostic.code in {"claim.predicate.unknown", "claim.property.unknown"}:
        message = f"Claim unknown {field} '{value}'"
    elif diagnostic.code == "claim.form.invalid":
        message = "Claim 形式は predicate/object または property/value のどちらか一方を完全に指定する"
    elif diagnostic.code in {
        "claim.predicate.domain_violation",
        "claim.predicate.range_violation",
        "claim.property.domain_violation",
    }:
        message = f"Claim {diagnostic}（型制約違反）"
    elif diagnostic.code == "claim.duplicate_relation":
        message = "relation と Claim の三つ組が重複"
    elif diagnostic.code == "claim.value.invalid_format":
        message = f"Claim {diagnostic}（year-expression の形式でない）"
    elif diagnostic.code == "claim.value_type.unknown":
        message = f"Claim {diagnostic}"
    else:
        # Future core diagnostics remain visible without making the adapter
        # depend on their wording.
        message = f"Claim {diagnostic}"
    return f"ERROR {path}: {message}"


def validate_claim(
    path: str,
    claim: Mapping[str, object],
    entities: Mapping[str, str],
    ontology,
    relation_edges: Iterable[tuple[str, str, str]],
) -> list[str]:
    """Validate through kb-ontology-core while preserving harness diagnostics."""
    core = load_core()
    return [_translate_diagnostic(path, diagnostic) for diagnostic in core.validate_claim(claim, entities, ontology, relation_edges)]
