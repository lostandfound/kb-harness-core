"""配布資産と対外契約が特定のエージェントランタイムに依存しないことを固定する。

ハーネスはすべてのランタイムで使う（AGENTS.md「ランタイム非依存」、
docs/notes/runtime-hiizon-memo.md）。ここに並べる語は、特定のランタイムへの依存を
見つけるための手がかりであり、対応ランタイムの一覧ではない。手順の前提としての依存
（サブエージェントが無いと成り立たない等）は語では捉えられないので、audit-harness が見る。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ランタイムの仕組みに合わせたアダプタで、ファイル全体が例外のもの。理由を必ず書く。
# Markdown の一部だけなら、ここに足さず <!-- runtime-adapter --> で囲む。
FILE_EXCEPTIONS = {
    "scripts/verify_turn.sh": "特定ランタイムのターン終了フックの入出力形式に合わせたアダプタ。無くても pre-commit が同じ検証を閉じる",
}

# 既知の語。大文字小文字を区別しない。ランタイム名と配置先は APM 0.32.0 の対象一覧
# （docs/notes/runtime-hiizon-memo.md「APM の仕様」）から採った。
PATTERNS = [
    # ランタイム・製品名
    r"\bclaude\b",
    r"\bcodex\b",
    r"\bcursor\b",
    r"\bcopilot\b",
    r"\bantigravity\b",
    r"\bgemini\b",
    r"\bwindsurf\b",
    r"\bkiro\b",
    r"\bopencode\b",
    r"\bgrok\b",
    r"\bhermes\b",
    r"\bopenclaw\b",
    # 配置先ディレクトリ・ランタイム固有の指示ファイル
    r"\.claude/",
    r"\.codex/",
    r"\.cursor/",
    r"\.agents/",
    r"\.gemini/",
    r"\.grok/",
    r"\.kiro/",
    r"\.opencode/",
    r"\.windsurf/",
    r"\.github/(?:agents|prompts|instructions)/",
    r"\bCLAUDE\.md\b",
    r"\bGEMINI\.md\b",
    # ランタイム固有のツール名
    r"\bWebFetch\b",
    r"\bWebSearch\b",
    r"\bAskUserQuestion\b",
    r"\bTodoWrite\b",
    r"\bMultiEdit\b",
    # モデル名
    r"\bsonnet\b",
    r"\bopus\b",
    r"\bhaiku\b",
    r"\bgpt-\d",
]
# ツール名として使われる語は、普通名詞と区別するため大文字始まりだけを拾う。
CASE_SENSITIVE_PATTERNS = [r"\bGrep\b", r"\bGlob\b"]

WORD_RE = re.compile("|".join(PATTERNS), re.IGNORECASE)
TOOL_RE = re.compile("|".join(CASE_SENSITIVE_PATTERNS))
ADAPTER_RE = re.compile(r"<!-- runtime-adapter -->.*?<!-- /runtime-adapter -->", re.DOTALL)
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
# プリミティブごとに、APM がどのランタイムにも写せるキーだけを許す。
ALLOWED_FRONTMATTER_KEYS = {
    "skills": {"name", "description"},
    "agents": {"name", "description"},
    "instructions": {"description", "applyTo"},
}


def scanned_files() -> list[Path]:
    files: set[Path] = set()
    files.update((ROOT / ".apm").rglob("*.md"))
    files.update(ROOT / name for name in ("README.md", "AGENTS.md"))
    files.update((ROOT / "docs").glob("*.md"))  # docs/notes/ は過去の記録なので対象外
    files.update(p for p in (ROOT / "scripts").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    files.update((ROOT / "src" / "kb_harness").rglob("*.py"))
    return sorted(files)


def strip_adapters(text: str) -> str:
    # 行番号を保つため、アダプタ区間は改行だけ残して消す。
    return ADAPTER_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


class RuntimeNeutralityTest(unittest.TestCase):
    def test_no_runtime_specific_terms(self):
        found = []
        for path in scanned_files():
            rel = path.relative_to(ROOT).as_posix()
            if rel in FILE_EXCEPTIONS:
                continue
            text = strip_adapters(path.read_text(encoding="utf-8"))
            for lineno, line in enumerate(text.splitlines(), 1):
                for match in [*WORD_RE.finditer(line), *TOOL_RE.finditer(line)]:
                    found.append(f"{rel}:{lineno}: {match.group(0)}")
        self.assertEqual(
            found,
            [],
            "特定ランタイムへの依存がある。能力で書き直すか、アダプタとして隔離する（AGENTS.md「ランタイム非依存」）",
        )

    def test_adapter_markers_are_balanced(self):
        for path in scanned_files():
            if path.suffix != ".md":
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                opens = text.count("<!-- runtime-adapter -->")
                closes = text.count("<!-- /runtime-adapter -->")
                self.assertEqual(opens, closes)
                self.assertEqual(len(ADAPTER_RE.findall(text)), opens)

    def test_file_exceptions_exist(self):
        for rel, reason in FILE_EXCEPTIONS.items():
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).is_file(), "例外一覧が存在しないファイルを指している")
                self.assertTrue(reason.strip())

    def test_asset_frontmatter_is_portable(self):
        for path in sorted((ROOT / ".apm").rglob("*.md")):
            match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            if not match:
                continue
            keys = {line.split(":", 1)[0].strip() for line in match.group(1).splitlines() if re.match(r"^[A-Za-z_][\w-]*:", line)}
            rel = path.relative_to(ROOT / ".apm")
            with self.subTest(path=rel.as_posix()):
                self.assertIn(rel.parts[0], ALLOWED_FRONTMATTER_KEYS, "未知のプリミティブ。許すキーを決めてから足す")
                self.assertLessEqual(keys, ALLOWED_FRONTMATTER_KEYS[rel.parts[0]], "frontmatter は APM がどのランタイムにも写せるキーだけにする。ツールの制限は本文に書く")

    def test_agents_are_thin_entries_to_skills(self):
        # エージェントは届かないランタイムがあるので、手順を持たずスキルを指すだけにする。
        skill_path_re = re.compile(r"apm_modules/lostandfound/kb-harness-core/\.apm/skills/([a-z0-9-]+)/SKILL\.md")
        for path in sorted((ROOT / ".apm" / "agents").glob("*.agent.md")):
            body = FRONTMATTER_RE.sub("", path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                skills = skill_path_re.findall(body)
                self.assertTrue(skills, "エージェントは従うスキルの正本のパスを示す")
                for name in skills:
                    self.assertTrue((ROOT / ".apm" / "skills" / name / "SKILL.md").is_file())
                self.assertNotIn("\n## ", body, "手順はスキルに書き、エージェントには見出しを持つ本文を置かない")


if __name__ == "__main__":
    unittest.main()
