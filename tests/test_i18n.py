# -*- coding: utf-8 -*-


def test_i18n_translation_keys():
    from integrated_app.i18n import t
    assert t("save", "zh-CN") == "保存"
    assert t("save", "en") == "Save"


def test_i18n_fallback():
    from integrated_app.i18n import t
    result = t("nonexistent_key", "zh-CN")
    assert result == "nonexistent_key"


def test_i18n_lang_map():
    from unittest.mock import MagicMock
    from integrated_app.i18n import get_lang

    req_zh = MagicMock()
    req_zh.query_params = {"lang": "zh"}
    req_zh.cookies = {}
    assert get_lang(req_zh) == "zh"

    req_jp = MagicMock()
    req_jp.query_params = {"lang": "jp"}
    req_jp.cookies = {}
    assert get_lang(req_jp) == "ja"

    req_kr = MagicMock()
    req_kr.query_params = {"lang": "kr"}
    req_kr.cookies = {}
    assert get_lang(req_kr) == "ko"
