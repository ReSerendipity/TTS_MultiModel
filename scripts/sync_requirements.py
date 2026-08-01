"""依赖一致性工具：保持 requirements.txt 与 pyproject.toml 的 dependencies 同步。

用法:
    python scripts/sync_requirements.py          # 从 pyproject.toml 重新生成 requirements.txt
    python scripts/sync_requirements.py --check  # 仅校验两者是否一致，不一致时以非零退出（CI 门禁）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"

HEADER = "# requirements.txt — 由 pyproject.toml 同步生成\n"


def load_pyproject_deps() -> list[str]:
    """读取 pyproject.toml 的 [project].dependencies 列表。"""
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    return [d.strip() for d in deps if d.strip()]


def load_requirements_deps() -> list[str]:
    """读取 requirements.txt 中的依赖声明（跳过注释与空行）。"""
    if not REQUIREMENTS.exists():
        return []
    deps: list[str] = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            deps.append(stripped)
    return deps


def check() -> int:
    """校验两个依赖源是否一致，不一致时返回 1。"""
    pyproject_deps = load_pyproject_deps()
    requirements_deps = load_requirements_deps()
    missing = [d for d in pyproject_deps if d not in requirements_deps]
    extra = [d for d in requirements_deps if d not in pyproject_deps]
    if not missing and not extra:
        print(f"OK: requirements.txt 与 pyproject.toml 一致（{len(pyproject_deps)} 个依赖）")
        return 0
    if missing:
        print("requirements.txt 缺少以下 pyproject.toml 依赖:", file=sys.stderr)
        for d in missing:
            print(f"  - {d}", file=sys.stderr)
    if extra:
        print("requirements.txt 包含 pyproject.toml 中不存在的依赖:", file=sys.stderr)
        for d in extra:
            print(f"  + {d}", file=sys.stderr)
    print("请运行: python scripts/sync_requirements.py", file=sys.stderr)
    return 1


def sync() -> int:
    """从 pyproject.toml 重新生成 requirements.txt。"""
    deps = load_pyproject_deps()
    content = HEADER + "\n".join(deps) + "\n"
    REQUIREMENTS.write_text(content, encoding="utf-8", newline="\n")
    print(f"已写入 {REQUIREMENTS}（{len(deps)} 个依赖）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步/校验 requirements.txt 与 pyproject.toml 依赖")
    parser.add_argument("--check", action="store_true", help="仅校验一致性，不一致时以非零退出")
    args = parser.parse_args()
    return check() if args.check else sync()


if __name__ == "__main__":
    sys.exit(main())
