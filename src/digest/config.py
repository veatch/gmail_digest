"""Load config.yml (small YAML subset, stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_UPSTREAM_PATHS = [
    "src",
    "scripts",
    "docs",
    ".github/workflows/digest.yml",
    "pyproject.toml",
    "uv.lock",
    "config.example.yml",
    ".python-version",
    ".gitignore",
]


@dataclass
class MailConfig:
    label: str = "INBOX"
    senders: list[str] = field(default_factory=list)
    lookback_days: int = 3
    max_messages: int = 20


@dataclass
class UpstreamConfig:
    auto_sync: bool = False
    url: str = ""
    ref: str = "main"
    paths: list[str] = field(default_factory=lambda: list(DEFAULT_UPSTREAM_PATHS))


@dataclass
class Config:
    mail: MailConfig = field(default_factory=MailConfig)
    upstream: UpstreamConfig = field(default_factory=UpstreamConfig)


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "" or value in {"null", "~", "Null", "NULL"}:
        return None
    if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
        return value[1:-1]
    lower = value.lower()
    if lower in {"true", "yes", "on"}:
        return True
    if lower in {"false", "no", "off"}:
        return False
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return value


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip()
    return line.rstrip()


def _child_kind(lines: list[str], start: int, parent_indent: int) -> str:
    """Return 'list', 'map', or 'empty' for the next nested block."""
    for original in lines[start:]:
        if not original.strip() or original.lstrip().startswith("#"):
            continue
        line = _strip_comment(original)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= parent_indent:
            return "empty"
        return "list" if line.strip().startswith("- ") else "map"
    return "empty"


def loads_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a minimal YAML subset: nested maps, lists, scalars, comments."""
    lines = text.splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for index, original in enumerate(lines):
        if not original.strip() or original.lstrip().startswith("#"):
            continue
        line = _strip_comment(original)
        if not line.strip():
            continue
        if "\t" in original[: len(original) - len(original.lstrip(" \t"))]:
            raise ValueError(f"line {index + 1}: tabs not allowed in indentation")

        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"line {index + 1}: list item under non-list parent")
            item_raw = content[2:].strip()
            parent.append(_parse_scalar(item_raw) if item_raw else None)
            continue

        if ":" not in content:
            raise ValueError(f"line {index + 1}: expected key: value, got {content!r}")

        key, _, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        if not isinstance(parent, dict):
            raise ValueError(f"line {index + 1}: mapping entry under non-map parent")

        if rest == "":
            kind = _child_kind(lines, index + 1, indent)
            child: Any = [] if kind == "list" else {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(rest)

    return root


def load_raw(path: Path | str) -> dict[str, Any]:
    return loads_simple_yaml(Path(path).read_text(encoding="utf-8"))


def config_from_mapping(data: dict[str, Any]) -> Config:
    mail_raw = data.get("mail") or {}
    upstream_raw = data.get("upstream") or {}
    if not isinstance(mail_raw, dict) or not isinstance(upstream_raw, dict):
        raise ValueError("mail and upstream must be mappings")

    senders = mail_raw.get("senders") or []
    if not isinstance(senders, list):
        raise ValueError("mail.senders must be a list")

    paths = upstream_raw.get("paths")
    if paths is None:
        paths = list(DEFAULT_UPSTREAM_PATHS)
    if not isinstance(paths, list):
        raise ValueError("upstream.paths must be a list")

    return Config(
        mail=MailConfig(
            label=str(mail_raw.get("label") or "INBOX"),
            senders=[str(s) for s in senders],
            lookback_days=int(mail_raw.get("lookback_days") or 3),
            max_messages=int(mail_raw.get("max_messages") or 20),
        ),
        upstream=UpstreamConfig(
            auto_sync=bool(upstream_raw.get("auto_sync") or False),
            url=str(upstream_raw.get("url") or "").strip(),
            ref=str(upstream_raw.get("ref") or "main").strip(),
            paths=[str(p) for p in paths],
        ),
    )


def load_config(path: Path | str = "config.yml") -> Config:
    return config_from_mapping(load_raw(path))


def find_config_path() -> Path | None:
    for candidate in (Path("config.yml"), Path("config.example.yml")):
        if candidate.is_file():
            return candidate
    return None
