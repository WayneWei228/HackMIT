"""Safe evaluation of arithmetic expressions produced by a model or a human.

Only numbers and + - * / ( ) are allowed. Dollar signs and thousands
separators are stripped before parsing. Anything else (power, calls,
names, attribute access, ...) raises ValueError.
"""

from __future__ import annotations

import ast
import operator

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def evaluate(expr: str) -> float:
    cleaned = expr.replace("$", "").replace(",", "")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression: {expr!r}") from exc
    return float(_eval_node(tree.body, expr))


def _eval_node(node: ast.AST, original: str):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"invalid expression: {original!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_node(node.left, original)
        right = _eval_node(node.right, original)
        return _ALLOWED_BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand, original))
    raise ValueError(f"invalid expression: {original!r}")
