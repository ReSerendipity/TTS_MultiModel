#!/usr/bin/env python3
"""断言：lock/钉版文件里每个版本都不低于 pyproject + requirements.txt 声明的下界。

背景（2026-09-20）：便携分卷的钉版集（`launcher/requirements-small.txt`、
`requirements-lock.txt`）里 `transformers==4.52.1` 低于 `pyproject.toml` 与
`requirements.txt` 同时声明的 `>=4.57.0`（该下界的理由写在 pyproject：
VoxCPM2 / IndexTTS2 的 tokenizer 与 modeling 需要较新 transformers API）。
钉版是为了便携包在真机上装得起来，但「装得起来」不等于「满足功能下界」——
一旦降级到线以下，随包分发的就是一个自称支持 VoxCPM2 却带着旧 transformers 的产物。

本脚本不猜该改哪一边，只把冲突摊开：任一 pin 低于任一声明下界即报违规。
`--allow-debt a,b` 是棘轮模式：名单内的存量违规只报不拦，名单外的新违规才 exit 1
（与 mypy 棘轮同一口径，避免为了存量债务给每个 PR 挂一条常红灯）。

用法：
    python scripts/check_pin_floors.py                        # 全部违规都拦
    python scripts/check_pin_floors.py --allow-debt transformers   # 只拦新增
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# 声明下界的来源（PEP 508 依赖行）
FLOOR_SOURCES = ("requirements.txt", "pyproject.toml")
# 钉版集：== 才算钉，>= 只是下界不参与比对
PINNED_SOURCES = ("requirements-lock.txt", "launcher/requirements-small.txt")

# 比对时忽略的包：与引擎无关的构建/工具链层，lock 里由解析器决定
IGNORE = {"pip", "setuptools", "wheel"}

_NAME_RE = re.compile(r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*(?P<spec>>=|==|~=|>|<=)\s*(?P<ver>[0-9][0-9a-zA-Z.+-]*)")


def _parse_ver(v: str) -> tuple:
    """版本串转成定长 4 元组，便于比较。

    先去掉本地版本段（``+cu132``）与预发布尾标（``rc0``/``a1``/``dev``），
    否则 ``2.13.0+cu132`` 里的 132 会被当成第四段，把 ``1.2.3.4`` 这类
    真四段版本压下去。预发布与正式版按同值处理（PEP 440 下 rc < 正式版），
    本脚本只判「是否低于下界」，该近似不影响结论。
    """
    core = re.split(r"[+]", v, maxsplit=1)[0]
    core = re.split(r"(?<=[\d.])(?:a|b|rc|dev|pre|post)\d*$", core)[0]
    nums = [int(n) for n in re.findall(r"\d+", core)[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def _iter_requirement_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-") or line.startswith("http"):
            continue
        out.append(line)
    return out


def collect_floors() -> dict[str, tuple[str, str]]:
    """返回 {包名小写: (下界版本, 来源)}，取多处声明中的最高下界。"""
    floors: dict[str, tuple[str, str]] = {}

    req = _ROOT / "requirements.txt"
    if req.exists():
        for line in _iter_requirement_lines(req.read_text(encoding="utf-8", errors="replace")):
            m = _NAME_RE.match(line)
            if m and m.group("spec") in (">=", "~=", ">"):
                _keep_higher(floors, m.group("name"), m.group("ver"), "requirements.txt")

    py = _ROOT / "pyproject.toml"
    if py.exists():
        in_deps = False
        for raw in py.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw.strip()
            if stripped.startswith("dependencies"):
                in_deps = True
                continue
            if in_deps and stripped.startswith("]"):
                in_deps = False
                continue
            if not in_deps:
                continue
            m = _NAME_RE.match(stripped.strip("\"'"))
            if m and m.group("spec") in (">=", "~=", ">"):
                _keep_higher(floors, m.group("name"), m.group("ver"), "pyproject.toml")

    return floors


def _keep_higher(floors: dict[str, tuple[str, str]], name: str, ver: str, src: str) -> None:
    key = name.lower().replace("_", "-")
    if key in IGNORE:
        return
    cur = floors.get(key)
    if cur is None or _parse_ver(ver) > _parse_ver(cur[0]):
        floors[key] = (ver, src)


def collect_pins() -> dict[str, tuple[str, str]]:
    """返回 {包名: (钉定版本, 出现该钉版的所有文件)}。

    同一个包可以在多个钉版集里各钉一次（lock 与便携 small 就是两套），
    必须全列出来——只报第一个会低估影响面：真正随包分发的是 small 那份。
    """
    found: dict[str, list[tuple[str, str]]] = {}
    for rel in PINNED_SOURCES:
        path = _ROOT / rel
        if not path.exists():
            continue
        for line in _iter_requirement_lines(path.read_text(encoding="utf-8", errors="replace")):
            m = _NAME_RE.match(line)
            if m and m.group("spec") == "==":
                key = m.group("name").lower().replace("_", "-")
                found.setdefault(key, []).append((m.group("ver"), rel))
    pins: dict[str, tuple[str, str]] = {}
    for key, hits in found.items():
        vers = {v for v, _ in hits}
        if len(vers) > 1:
            # 两套钉版集自己就不一致：取最低值参与下界比对（最保守）
            low = min(vers, key=_parse_ver)
            pins[key] = (low, "、".join(f"{v}@{r}" for v, r in hits))
        else:
            pins[key] = (hits[0][0], "、".join(r for _, r in hits))
    return pins


def find_violations(floors: dict, pins: dict) -> list[str]:
    out = []
    for name, (pinned, src) in sorted(pins.items()):
        floor = floors.get(name)
        if not floor:
            continue
        floor_ver, floor_src = floor
        if _parse_ver(pinned) < _parse_ver(floor_ver):
            out.append(f"{name}: {src} 钉 {pinned} < {floor_src} 声明的下界 {floor_ver}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查钉版是否低于声明下界")
    ap.add_argument("--quiet", action="store_true", help="只输出违规项")
    ap.add_argument(
        "--allow-debt",
        default="",
        help="逗号分隔的存量违规包名：这些只报不拦，出现名单外的新违规才 exit 1",
    )
    args = ap.parse_args(argv)

    floors = collect_floors()
    pins = collect_pins()
    violations = find_violations(floors, pins)
    allowed = {n.strip().lower() for n in args.allow_debt.split(",") if n.strip()}

    if not args.quiet:
        print(f"[pin-floors] 声明下界 {len(floors)} 项，钉版 {len(pins)} 项")
    blocking = []
    for v in violations:
        name = v.split(":", 1)[0].strip()
        if name in allowed:
            print(f"  [已知存量] {v}")
        else:
            blocking.append(v)
            print(f"  [FAIL] {v}")

    if blocking:
        print(
            f"\n[pin-floors] {len(blocking)} 处违规：要么把钉版升到下界以上并重新做便携包解析，"
            "要么在 pyproject/requirements 里显式降低下界并说明理由。",
            file=sys.stderr,
        )
        return 1
    if violations:
        print(f"[pin-floors] 仅存量违规（{sorted(allowed)}），修好后请同步删掉 --allow-debt")
    else:
        print("[pin-floors] PASS 无钉版低于声明下界")
    return 0


if __name__ == "__main__":
    sys.exit(main())
