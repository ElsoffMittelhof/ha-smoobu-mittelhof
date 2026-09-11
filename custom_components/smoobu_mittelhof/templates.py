"""External mail template repository and Smoobu-style placeholder renderer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml

_TEMPLATE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_PLACEHOLDER = re.compile(r"\[([A-Za-z0-9_]+)\]")


class TemplateError(Exception):
    pass


@dataclass(slots=True)
class MailTemplate:
    name: str
    subject: str
    body: str
    required_placeholders: list[str]


class TemplateRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def load(self, name: str) -> MailTemplate:
        if not _TEMPLATE_NAME.fullmatch(name):
            raise TemplateError("Invalid template name")
        path = self.directory / f"{name}.yaml"
        if not path.is_file():
            raise TemplateError(f"Template not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise TemplateError("Template YAML must contain a mapping")
        return MailTemplate(
            name=name,
            subject=str(data.get("subject") or ""),
            body=str(data.get("body") or ""),
            required_placeholders=[str(v).strip("[]") for v in (data.get("required_placeholders") or [])],
        )

    @staticmethod
    def render(template: MailTemplate, values: dict[str, Any]) -> dict[str, Any]:
        normalized = {str(key).strip("[]"): "" if value is None else str(value) for key, value in values.items()}
        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            return normalized.get(key, match.group(0))
        subject = _PLACEHOLDER.sub(repl, template.subject)
        body = _PLACEHOLDER.sub(repl, template.body)
        unresolved = sorted(set(_PLACEHOLDER.findall(subject + "\n" + body)))
        missing_required = sorted(
            key for key in template.required_placeholders if not normalized.get(key, "").strip()
        )
        return {
            "template": template.name,
            "subject": subject,
            "body": body,
            "unresolved": unresolved,
            "missing_required": missing_required,
            "valid": not missing_required,
        }
