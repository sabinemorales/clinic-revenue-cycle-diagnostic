import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_banner_text_is_exact():
    source = APP.read_text()
    assert 'BANNER = "Synthetic data — illustrative only"' in source


def test_every_view_renders_the_banner_before_the_branch():
    tree = ast.parse(APP.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    calls_before_branch = []
    saw_branch = False
    for statement in main.body:
        if isinstance(statement, ast.If):
            saw_branch = True
            break
        calls_before_branch.extend(_call_names(statement))
    assert saw_branch
    assert "render_banner" in calls_before_branch


def _call_names(node: ast.AST) -> list[str]:
    names = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            names.append(child.func.id)
    return names
