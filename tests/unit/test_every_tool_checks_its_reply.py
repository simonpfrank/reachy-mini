"""Every tool's reply goes through reachy_lib.replies: a tool added without the check fails here."""

import ast
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"


def tool_calls():
    """Each Tool subclass's async __call__ in robot_tools, as (file, class, function node)."""
    for path in sorted(TOOLS.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id == "Tool" for b in node.bases):
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and item.name == "__call__":
                        yield path.name, node.name, item


def test_the_guard_actually_finds_the_tools():
    assert len(list(tool_calls())) >= 12


def test_every_tool_reply_goes_through_the_check():
    unchecked = [
        f"{file}:{name}"
        for file, name, function in tool_calls()
        if not any(isinstance(d, ast.Name) and d.id == "checked" for d in function.decorator_list)
    ]
    assert unchecked == []
