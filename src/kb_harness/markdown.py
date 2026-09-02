"""Markdown documents with YAML frontmatter."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
