"""Guard the Python-and-browser-native source boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_SUFFIXES = {".t" + "s", ".t" + "sx", ".mt" + "s", ".ct" + "s"}
FORBIDDEN_NAMES = {
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "ts" + "config.json",
}
SKIPPED_PARTS = {".git", ".venv", "__pycache__"}


def test_tracked_source_uses_python_and_native_browser_assets_only() -> None:
    forbidden: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or set(path.parts) & SKIPPED_PARTS:
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name in FORBIDDEN_NAMES:
            forbidden.append(str(path.relative_to(ROOT)))
    assert not forbidden, f"Unsupported source/toolchain files: {forbidden}"
