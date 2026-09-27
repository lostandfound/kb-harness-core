"""Markdown documents with YAML frontmatter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

import yaml

from .diagnostics import Diagnostic, HarnessError


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Document:
    path: str
    frontmatter: Mapping[str, object]
    body: str


def parse_document(path: str, text: str) -> Document:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise HarnessError(
            Diagnostic(
                code="markdown.frontmatter_missing",
                message="frontmatter not found",
                path=path,
            )
        )
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        raise HarnessError(
            Diagnostic(
                code="markdown.frontmatter_invalid",
                message=f"frontmatter parse error: {error}",
                path=path,
            )
        ) from error
    if not isinstance(frontmatter, dict):
        raise HarnessError(
            Diagnostic(
                code="markdown.frontmatter_not_mapping",
                message="frontmatter must be a mapping",
                path=path,
            )
        )
    return Document(path=path, frontmatter=frontmatter, body=match.group(2))


def frontmatter_scalar_text(text: str, key: str) -> str | None:
    """マージキーで継承した値も含め、YAML スカラーの元の表記を返す。"""
    frontmatter = FRONTMATTER_RE.match(text).group(1)
    loader = yaml.SafeLoader(frontmatter)
    try:
        node = loader.get_single_node()
        loader.flatten_mapping(node)
        return next((value.value for name, value in reversed(node.value) if name.value == key), None)
    finally:
        loader.dispose()


def field_text(value: object) -> str | None:
    """型固有フィールドの値を検査用の文字列にする。

    YAML は `year: 2021` を int、`date: 2021-05-01` を date として読むが、
    フィールドは文字列として扱う契約なので、これらのスカラーは文字列表現に写す。
    文字列でもスカラーでもない値（None / bool / list / dict）は None を返す。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None
