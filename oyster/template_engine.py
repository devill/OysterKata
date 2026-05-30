"""A minimal Handlebars-ish template engine.

Pure Python, no third-party dependencies. Supports a deliberately small subset
of Handlebars that the invoice template needs:

- ``{{ path }}``   interpolation, HTML-escaped, dotted paths supported.
- ``{{{ path }}}`` interpolation without escaping (raw).
- ``{{#each items}} ... {{/each}}`` iteration over a list.
- ``{{#if cond}} ... {{else}} ... {{/if}}`` conditional on truthiness.
- ``{{#unless cond}} ... {{/unless}}`` inverse conditional.

Inside an ``each`` block ``{{ this }}`` is the current item, ``{{ this.field }}``
and bare ``{{ field }}`` resolve against the current item (falling back to the
enclosing context), and ``{{@index}}`` / ``{{@first}}`` / ``{{@last}}`` are
available.

Resolution is forgiving: a missing path renders as an empty string. Structure is
strict: an unclosed or mismatched block tag raises :class:`TemplateError`.

The design is a small pipeline: ``tokenize`` -> ``parse`` (a recursive descent
producing a node tree) -> ``Node.render``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


class TemplateError(Exception):
    """Raised for malformed templates (unclosed or mismatched block tags)."""


_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}


def _html_escape(value: str) -> str:
    return "".join(_ESCAPES.get(char, char) for char in value)


# --- Tokenizer ------------------------------------------------------------

# A tag is anything between {{ and }}. We match the triple-brace form first so
# that {{{ raw }}} is not mistaken for a {{ raw } interpolation.
_TAG = re.compile(r"\{\{\{\s*(.*?)\s*\}\}\}|\{\{\s*(.*?)\s*\}\}", re.DOTALL)


@dataclass(frozen=True)
class _Token:
    kind: str  # "text", "var", "raw", "block_open", "block_close", "else"
    value: str  # text content, or the path / block expression


def _classify_tag(inner: str, raw: bool) -> _Token:
    if raw:
        return _Token("raw", inner)
    if inner.startswith("#"):
        return _Token("block_open", inner[1:].strip())
    if inner.startswith("/"):
        return _Token("block_close", inner[1:].strip())
    if inner == "else":
        return _Token("else", "")
    return _Token("var", inner)


def tokenize(template: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    for match in _TAG.finditer(template):
        if match.start() > pos:
            tokens.append(_Token("text", template[pos : match.start()]))
        raw_inner, var_inner = match.group(1), match.group(2)
        if raw_inner is not None:
            tokens.append(_classify_tag(raw_inner.strip(), raw=True))
        else:
            tokens.append(_classify_tag(var_inner.strip(), raw=False))
        pos = match.end()
    if pos < len(template):
        tokens.append(_Token("text", template[pos:]))
    return tokens


# --- Node tree ------------------------------------------------------------


class _Node:
    def render(self, context: "_Scope") -> str:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class _Text(_Node):
    text: str

    def render(self, context: "_Scope") -> str:
        return self.text


@dataclass
class _Interpolation(_Node):
    path: str
    escape: bool

    def render(self, context: "_Scope") -> str:
        value = _stringify(context.resolve(self.path))
        return _html_escape(value) if self.escape else value


@dataclass
class _Each(_Node):
    path: str
    body: list[_Node] = field(default_factory=list)

    def render(self, context: "_Scope") -> str:
        items = context.resolve(self.path)
        if not isinstance(items, (list, tuple)):
            return ""
        out: list[str] = []
        last = len(items) - 1
        for index, item in enumerate(items):
            scope = context.child(
                item,
                index=index,
                first=index == 0,
                last=index == last,
            )
            out.extend(node.render(scope) for node in self.body)
        return "".join(out)


@dataclass
class _Conditional(_Node):
    path: str
    negate: bool  # True for {{#unless}}
    body: list[_Node] = field(default_factory=list)
    else_body: list[_Node] = field(default_factory=list)

    def render(self, context: "_Scope") -> str:
        truthy = _is_truthy(context.resolve(self.path))
        chosen = self.body if (truthy != self.negate) else self.else_body
        return "".join(node.render(context) for node in chosen)


# --- Parser ---------------------------------------------------------------

_BLOCK_KEYWORDS = {"each", "if", "unless"}


def _split_block(expr: str) -> tuple[str, str]:
    parts = expr.split(None, 1)
    keyword = parts[0]
    argument = parts[1].strip() if len(parts) > 1 else ""
    return keyword, argument


def parse(tokens: list[_Token]) -> list[_Node]:
    nodes, consumed = _parse_until(tokens, 0, expected_close=None)
    if consumed != len(tokens):
        raise TemplateError("unexpected trailing tokens after parse")
    return nodes


def _parse_until(
    tokens: list[_Token], start: int, expected_close: str | None
) -> tuple[list[_Node], int]:
    """Parse nodes from ``start`` until the matching close tag (or end).

    Returns the node list and the index just past the consumed tokens. For a
    top-level call ``expected_close`` is ``None`` and parsing stops at the end
    of the token stream.
    """
    nodes: list[_Node] = []
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token.kind == "text":
            nodes.append(_Text(token.value))
            index += 1
        elif token.kind == "var":
            nodes.append(_Interpolation(token.value, escape=True))
            index += 1
        elif token.kind == "raw":
            nodes.append(_Interpolation(token.value, escape=False))
            index += 1
        elif token.kind == "block_open":
            node, index = _parse_block(tokens, index)
            nodes.append(node)
        elif token.kind == "block_close":
            if token.value != expected_close:
                raise TemplateError(
                    f"unexpected closing tag {{{{/{token.value}}}}}"
                    + (
                        f" (expected {{{{/{expected_close}}}}})"
                        if expected_close
                        else ""
                    )
                )
            return nodes, index + 1
        elif token.kind == "else":
            # An {{else}} only makes sense inside an if/unless block, which is
            # handled by _parse_block. Encountering it here is a structure error.
            raise TemplateError("{{else}} outside of an {{#if}}/{{#unless}} block")
    if expected_close is not None:
        raise TemplateError(f"missing closing tag {{{{/{expected_close}}}}}")
    return nodes, index


def _parse_block(tokens: list[_Token], index: int) -> tuple[_Node, int]:
    keyword, argument = _split_block(tokens[index].value)
    if keyword not in _BLOCK_KEYWORDS:
        raise TemplateError(f"unknown block helper {{{{#{keyword}}}}}")
    if not argument:
        raise TemplateError(f"{{{{#{keyword}}}}} requires an argument")

    if keyword == "each":
        body, after = _parse_until(tokens, index + 1, expected_close="each")
        return _Each(argument, body), after

    # if / unless share a body + optional {{else}} branch.
    main_body, else_body, after = _parse_branch(tokens, index + 1, keyword)
    return (
        _Conditional(argument, negate=keyword == "unless", body=main_body, else_body=else_body),
        after,
    )


def _parse_branch(
    tokens: list[_Token], start: int, keyword: str
) -> tuple[list[_Node], list[_Node], int]:
    """Parse an if/unless body, splitting on an optional top-level {{else}}."""
    main_body: list[_Node] = []
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token.kind == "else":
            else_body, after = _parse_until(tokens, index + 1, expected_close=keyword)
            return main_body, else_body, after
        if token.kind == "block_close":
            if token.value != keyword:
                raise TemplateError(
                    f"unexpected closing tag {{{{/{token.value}}}}} "
                    f"(expected {{{{/{keyword}}}}})"
                )
            return main_body, [], index + 1
        node, index = _parse_one(tokens, index)
        main_body.append(node)
    raise TemplateError(f"missing closing tag {{{{/{keyword}}}}}")


def _parse_one(tokens: list[_Token], index: int) -> tuple[_Node, int]:
    token = tokens[index]
    if token.kind == "text":
        return _Text(token.value), index + 1
    if token.kind == "var":
        return _Interpolation(token.value, escape=True), index + 1
    if token.kind == "raw":
        return _Interpolation(token.value, escape=False), index + 1
    if token.kind == "block_open":
        return _parse_block(tokens, index)
    raise TemplateError(f"unexpected token {token.kind!r} while parsing block body")


# --- Resolution scope -----------------------------------------------------


class _Scope:
    """A lookup chain: the current value plus its enclosing scope.

    Resolution rules:
    - ``this`` / ``.`` -> the current value.
    - ``@index`` / ``@first`` / ``@last`` -> iteration metadata.
    - ``this.field`` -> ``field`` on the current value.
    - bare ``field`` -> ``field`` on the current value, else the parent scope.
    - dotted ``a.b.c`` -> walk from the current value, else from the parent.
    """

    def __init__(self, value, parent: "_Scope | None" = None, meta: dict | None = None):
        self.value = value
        self.parent = parent
        self.meta = meta or {}

    def child(self, value, *, index: int, first: bool, last: bool) -> "_Scope":
        return _Scope(
            value,
            parent=self,
            meta={"index": index, "first": first, "last": last},
        )

    def resolve(self, path: str):
        if path in ("this", "."):
            return self.value
        if path.startswith("@"):
            return self._resolve_meta(path[1:])
        if path.startswith("this."):
            return _walk(self.value, path[len("this.") :])
        found, value = self._lookup(path)
        return value if found else None

    def _resolve_meta(self, name: str):
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.meta:
                return scope.meta[name]
            scope = scope.parent
        return None

    def _lookup(self, path: str) -> tuple[bool, object]:
        found, value = _try_walk(self.value, path)
        if found:
            return True, value
        if self.parent is not None:
            return self.parent._lookup(path)
        return False, None


def _try_walk(value, path: str) -> tuple[bool, object]:
    """Walk a dotted path from ``value``; return (found, result)."""
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return False, None
    return True, current


def _walk(value, path: str):
    found, result = _try_walk(value, path)
    return result if found else None


# --- Helpers --------------------------------------------------------------


def _is_truthy(value) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (str, list, tuple, dict)):
        return len(value) > 0
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def _stringify(value) -> str:
    if value is None or value is False:
        return ""
    if value is True:
        return "true"
    return str(value)


# --- Public API -----------------------------------------------------------


def render(template: str, context: dict) -> str:
    nodes = parse(tokenize(template))
    scope = _Scope(context)
    return "".join(node.render(scope) for node in nodes)


def render_file(path: str | Path, context: dict) -> str:
    return render(Path(path).read_text(encoding="utf-8"), context)
