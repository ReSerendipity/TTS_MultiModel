"""`scripts/check_pin_floors.py` 的行为测试。

注意：本仓库当前**存在一处已知违规**（transformers 钉 4.52.1 < 声明下界 4.57.0），
所以这里不断言「全仓库无违规」——那会是一条假的绿。
改为棘轮：只允许已知违规存在，新出现的违规直接红（与 mypy 棘轮同一口径）。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

import check_pin_floors as cpf  # noqa: E402

# 当前唯一被接受的存量违规；修好后请把这个集合清空
KNOWN_DEBT = {"transformers"}


class TestParseVer:
    def test_numeric_ordering(self):
        assert cpf._parse_ver("4.57.0") > cpf._parse_ver("4.52.1")
        assert cpf._parse_ver("4.57.0") < cpf._parse_ver("4.100.0")

    def test_local_version_suffix_uses_numeric_prefix(self):
        assert cpf._parse_ver("2.13.0+cu132") == cpf._parse_ver("2.13.0")
        assert cpf._parse_ver("2.13.0+cu132") > cpf._parse_ver("2.5.1")

    def test_suffix_digits_do_not_outrank_a_real_fourth_segment(self):
        """回归：早期实现把 +cu132 的 132 当第四段，会压过 1.2.3.4。"""
        assert cpf._parse_ver("1.2.3+cu999") == cpf._parse_ver("1.2.3")
        assert cpf._parse_ver("1.2.3.4") > cpf._parse_ver("1.2.3+cu999")

    def test_prerelease_marker_treated_as_base_version(self):
        assert cpf._parse_ver("4.57.0rc0") == cpf._parse_ver("4.57.0")


class TestFindViolations:
    def test_pin_below_floor_is_reported(self):
        floors = {"widget": ("1.4.0", "requirements.txt")}
        pins = {"widget": ("1.3.9", "requirements-lock.txt")}
        out = cpf.find_violations(floors, pins)
        assert len(out) == 1 and "widget" in out[0]

    def test_pin_equal_to_floor_passes(self):
        floors = {"widget": ("1.4.0", "requirements.txt")}
        pins = {"widget": ("1.4.0", "requirements-lock.txt")}
        assert cpf.find_violations(floors, pins) == []

    def test_pin_above_floor_passes(self):
        floors = {"widget": ("1.4.0", "pyproject.toml")}
        pins = {"widget": ("2.0.0", "requirements-lock.txt")}
        assert cpf.find_violations(floors, pins) == []

    def test_package_without_declared_floor_is_ignored(self):
        pins = {"mystery": ("0.1", "requirements-lock.txt")}
        assert cpf.find_violations({}, pins) == []


class TestFloorCollection:
    def test_highest_declared_floor_wins(self):
        floors: dict = {}
        cpf._keep_higher(floors, "transformers", "4.52.1", "requirements.txt")
        cpf._keep_higher(floors, "transformers", "4.57.0", "pyproject.toml")
        assert floors["transformers"] == ("4.57.0", "pyproject.toml")
        cpf._keep_higher(floors, "transformers", "4.53.0", "requirements.txt")
        assert floors["transformers"] == ("4.57.0", "pyproject.toml")

    def test_name_normalization_unifies_underscore_and_dash(self):
        floors: dict = {}
        cpf._keep_higher(floors, "some_pkg", "1.0", "requirements.txt")
        assert "some-pkg" in floors

    def test_ignore_list_excludes_build_tools(self):
        floors: dict = {}
        cpf._keep_higher(floors, "wheel", "0.45", "requirements.txt")
        assert floors == {}


class TestRepoState:
    """棘轮：仓库真实状态里不允许出现新的违规。"""

    def test_no_new_violations_beyond_known_debt(self):
        names = {v.split(":", 1)[0].strip() for v in cpf.find_violations(cpf.collect_floors(), cpf.collect_pins())}
        assert names <= KNOWN_DEBT, f"新增钉版低于下界：{sorted(names - KNOWN_DEBT)}"

    def test_declared_floor_for_transformers_is_actually_parsed(self):
        """存量违规必须仍被检测到，否则说明解析器坏了、棘轮会变成空过。"""
        floors = cpf.collect_floors()
        assert "transformers" in floors
        names = {v.split(":", 1)[0].strip() for v in cpf.find_violations(floors, cpf.collect_pins())}
        assert "transformers" in names or not KNOWN_DEBT, "解析器可能失效：已知违规不见了"

    def test_both_pinned_files_are_attributed(self):
        """便携包真正随包分发的是 launcher 那份，漏报会低估影响面。"""
        pins = cpf.collect_pins()
        src = pins["transformers"][1]
        assert "requirements-lock.txt" in src
        assert "launcher/requirements-small.txt" in src
