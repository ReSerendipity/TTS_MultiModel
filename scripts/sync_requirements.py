# -*- coding: utf-8 -*-
"""从 pyproject.toml 同步生成 requirements.txt"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sync():
    pyproject = ROOT / "pyproject.toml"
    requirements = ROOT / "requirements.txt"

    with open(pyproject, "rb") as f:
        data = tomllib.load(f)

    deps = data["project"]["dependencies"]
    header = "# requirements.txt — 由 pyproject.toml 同步生成\n"

    with open(requirements, "w", encoding="utf-8") as f:
        f.write(header)
        for dep in deps:
            f.write(dep + "\n")

    print(f"已同步 {len(deps)} 个依赖到 {requirements}")


def check():
    pyproject = ROOT / "pyproject.toml"
    requirements = ROOT / "requirements.txt"

    with open(pyproject, "rb") as f:
        deps = tomllib.load(f)["project"]["dependencies"]

    with open(requirements, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]

    if set(deps) != set(lines):
        missing = set(deps) - set(lines)
        extra = set(lines) - set(deps)
        print(f"依赖不一致！缺失: {missing}, 多余: {extra}")
        sys.exit(1)
    print("依赖一致性检查通过")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        sync()
