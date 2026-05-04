"""Extract analyzable blocks (functions, methods, nested functions) from a
Python source file.

Classes themselves are NOT emitted as rows — only the functions/methods inside
them. Methods are named `ClassName.method`; nested defs are `outer.inner` and
methods inside nested classes are `Outer.Inner.foo`.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    name: str   # e.g. "foo", "Bar.baz", "Outer.Inner.qux"
    start: int  # 1-indexed first line (the `def`/`async def`)
    end: int    # 1-indexed last line, inclusive


_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def extract_blocks(src: str) -> list[Block]:
    """Return one Block per def in the source, in document order. Returns []
    if the source can't be parsed."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    blocks: list[Block] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _FUNC_NODES):
                name = f"{prefix}{child.name}"
                end = getattr(child, "end_lineno", child.lineno) or child.lineno
                blocks.append(Block(name=name, start=child.lineno, end=end))
                walk(child, prefix=f"{name}.")
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix=f"{prefix}{child.name}.")

    walk(tree, prefix="")
    return blocks
