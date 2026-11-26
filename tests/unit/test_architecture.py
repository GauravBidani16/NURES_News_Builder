"""Architecture tests to enforce dependency boundaries.

Rule: news_post_builder.core must NOT import from adapters or web.
"""

import ast
from pathlib import Path


def test_core_does_not_import_adapters_or_web() -> None:
    core_dir = Path(__file__).resolve().parent.parent.parent / "src" / "news_post_builder" / "core"
    assert core_dir.exists(), f"Core directory not found at {core_dir}"

    python_files = list(core_dir.glob("**/*.py"))
    forbidden_prefixes = (
        "news_post_builder.adapters",
        "news_post_builder.web",
        ".adapters",
        ".web",
        "..adapters",
        "..web",
    )

    violations: list[str] = []

    for file_path in python_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        if alias.name.startswith(prefix):
                            violations.append(
                                f"{file_path.name}:{node.lineno} imports '{alias.name}'"
                            )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for prefix in forbidden_prefixes:
                    if module.startswith(prefix):
                        violations.append(f"{file_path.name}:{node.lineno} imports from '{module}'")

    assert not violations, "Core layer imports forbidden modules (adapters/web):\n" + "\n".join(
        violations
    )
