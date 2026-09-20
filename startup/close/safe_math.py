"""Re-evaluate arithmetic an LLM wrote. Nothing but numbers and + - * / ( ) survives."""

from __future__ import annotations

import ast
import re

ALLOWED = re.compile(r"^[0-9+\-*/(). \t]+$")
_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_UNARYOPS = (ast.UAdd, ast.USub)


def evaluate(expression: str) -> float:
    """Evaluate a plain arithmetic string; anything else raises ValueError."""
    if not isinstance(expression, str):
        raise ValueError(f"not an expression: {expression!r}")
    cleaned = expression.replace("$", "").replace(",", "").strip()
    if not cleaned or not ALLOWED.match(cleaned):
        raise ValueError(f"unsupported characters in expression: {expression!r}")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"not an arithmetic expression: {expression!r}") from exc
    _check(tree.body, expression)
    try:
        return float(eval(compile(tree, "<safe_math>", "eval"), {"__builtins__": {}}, {}))
    except ZeroDivisionError as exc:
        raise ValueError(f"division by zero: {expression!r}") from exc


def _check(node: ast.AST, expression: str) -> None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINOPS):
        _check(node.left, expression)
        _check(node.right, expression)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, _UNARYOPS):
        _check(node.operand, expression)
    elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return
    else:
        raise ValueError(f"unsupported syntax in expression: {expression!r}")
