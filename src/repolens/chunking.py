"""Split source files into Chunks at function and class boundaries."""

from dataclasses import dataclass
from pathlib import PurePosixPath

import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

# Part of each Snapshot's index version: bump it when a change here changes the Chunks of a
# repository, so Snapshots ingested before the change are ingested again.
CHUNKER_VERSION = 2

MODULE_SYMBOL = "<module>"
MAX_CHUNK_LINES = 150
# Module-level code shorter than this joins the definition next to it.
SMALL_MODULE_LINES = 10

LANGUAGES = {
    ".py": Language(tree_sitter_python.language()),
    ".ts": Language(tree_sitter_typescript.language_typescript()),
    ".tsx": Language(tree_sitter_typescript.language_tsx()),
}

# Nodes that wrap a definition: Python decorators and TypeScript `export`.
_WRAPPERS = {"decorated_definition": "definition", "export_statement": "declaration"}
_CLASSES = {"class_definition", "class_declaration", "abstract_class_declaration"}
_DEFINITIONS = _CLASSES | {
    "function_definition",
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
}
_FUNCTION_VALUES = {"arrow_function", "function_expression"}


@dataclass(frozen=True)
class Chunk:
    path: str
    start_line: int
    end_line: int
    symbol: str
    text: str


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    symbol: str


def chunk_file(path: str, source: str) -> list[Chunk]:
    """Split one file into Chunks. Line numbers are 1-based and inclusive."""
    language = LANGUAGES[PurePosixPath(path).suffix]
    tree = Parser(language).parse(source.encode())
    lines = source.split("\n")  # tree-sitter rows count "\n" only
    return [
        Chunk(path, w.start + 1, w.end + 1, w.symbol, "\n".join(lines[w.start : w.end + 1]))
        for span in _merge_small_module_code(
            _spans(tree.root_node.named_children, MODULE_SYMBOL, None)
        )
        for w in _windows(span)
    ]


def _spans(children: list[Node], container: str, header: tuple[int, int] | None) -> list[_Span]:
    """Give each definition its own span and group the code between them under `container`.

    A class longer than MAX_CHUNK_LINES is split the same way, one span per method.
    """
    spans: list[_Span] = []
    loose = header
    for child in children:
        definition = _definition(child)
        if definition is None:
            loose = (loose[0] if loose else child.start_point.row, child.end_point.row)
            continue
        if loose:
            spans.append(_Span(loose[0], loose[1], container))
            loose = None
        name, body = definition
        symbol = name if container == MODULE_SYMBOL else f"{container}.{name}"
        start, end = child.start_point.row, child.end_point.row
        if body is not None and end - start + 1 > MAX_CHUNK_LINES:
            header_end = body.prev_sibling.end_point.row if body.prev_sibling else start
            spans.extend(_spans(body.named_children, symbol, (start, header_end)))
        else:
            spans.append(_Span(start, end, symbol))
    if loose:
        spans.append(_Span(loose[0], loose[1], container))
    return spans


def _merge_small_module_code(spans: list[_Span]) -> list[_Span]:
    """Join short module-level code, like imports or `if __name__ == "__main__":`, to the
    definition after it, or before it at the end of a file, so few Chunks are a few loose lines.
    """
    merged: list[_Span] = []
    small: _Span | None = None
    for span in spans:
        if span.symbol == MODULE_SYMBOL and span.end - span.start + 1 < SMALL_MODULE_LINES:
            if small:
                merged.append(small)
            small = span
            continue
        if small and span.end - small.start + 1 <= MAX_CHUNK_LINES:
            span = _Span(small.start, span.end, span.symbol)
        elif small:
            merged.append(small)
        small = None
        merged.append(span)
    if small and merged and small.end - merged[-1].start + 1 <= MAX_CHUNK_LINES:
        merged[-1] = _Span(merged[-1].start, small.end, merged[-1].symbol)
    elif small:
        merged.append(small)
    return merged


def _definition(node: Node) -> tuple[str, Node | None] | None:
    """Return a definition's name, plus its body if it is a class."""
    if node.type in _WRAPPERS:
        inner = node.child_by_field_name(_WRAPPERS[node.type])
        return _definition(inner) if inner else None
    if node.type == "lexical_declaration" and len(node.named_children) == 1:
        # `const handler = () => {...}`
        declarator = node.named_children[0]
        value = declarator.child_by_field_name("value")
        if value is None or value.type not in _FUNCTION_VALUES:
            return None
        node = declarator
    elif node.type not in _DEFINITIONS:
        return None
    name = node.child_by_field_name("name")
    if name is None or name.text is None:
        return None
    body = node.child_by_field_name("body") if node.type in _CLASSES else None
    return name.text.decode(), body


def _windows(span: _Span) -> list[_Span]:
    return [
        _Span(start, min(start + MAX_CHUNK_LINES - 1, span.end), span.symbol)
        for start in range(span.start, span.end + 1, MAX_CHUNK_LINES)
    ]
