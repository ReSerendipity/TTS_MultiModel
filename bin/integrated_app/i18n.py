import json
import os
from typing import Any

_LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

_LANG_FILE_MAP = {
    "en": "en.json",
    "zh-CN": "zh.json",
    "zh-Hans": "zh.json",
    "zh": "zh.json",
    "ja": "ja.json",
    "ko": "ko.json",
}

_I18N_TRANSLATIONS: dict[str, Any] = {}


def _load_translations(lang):
    if lang in _I18N_TRANSLATIONS:
        return _I18N_TRANSLATIONS[lang]
    filename = _LANG_FILE_MAP.get(lang)
    if filename is None:
        return None
    filepath = os.path.join(_LOCALES_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    _I18N_TRANSLATIONS[lang] = data
    return data


def _resolve_key(translations, key):
    if "." in key:
        parts = key.split(".")
        result = translations
        for part in parts:
            if isinstance(result, dict) and part in result:
                result = result[part]
            else:
                return None
        return result if isinstance(result, str) else None
    return translations.get(key)


_DEFAULT_LANG = "zh-CN"


def t(key, lang=_DEFAULT_LANG, default=None):
    lang_dict = _load_translations(lang)
    if lang_dict is not None:
        result = _resolve_key(lang_dict, key)
        if result is not None:
            return result
    en_dict = _load_translations("en")
    if en_dict is not None:
        result = _resolve_key(en_dict, key)
        if result is not None:
            return result
    return default if default is not None else key


def get_lang(request):
    lang = request.query_params.get("lang")
    if lang:
        if lang in _LANG_FILE_MAP:
            return lang
        lang_map = {"zh": "zh-CN", "ja": "ja", "jp": "ja", "ko": "ko", "kr": "ko", "en": "en"}
        if lang in lang_map:
            return lang_map[lang]
    lang = request.cookies.get("lang")
    if lang:
        if lang in _LANG_FILE_MAP:
            return lang
        lang_map = {"zh": "zh-CN", "ja": "ja", "jp": "ja", "ko": "ko", "kr": "ko", "en": "en"}
        if lang in lang_map:
            return lang_map[lang]
    return _DEFAULT_LANG


def register_i18n_filters(env):
    env.filters["t"] = t


class _I18NCallable:
    def __call__(self, key, lang=_DEFAULT_LANG):
        return t(key, lang)

    def __repr__(self):
        en_dict = _load_translations("en")
        return f"I18N(keys={len(en_dict) if en_dict else 0})"


I18N = _I18NCallable()


def get_i18n_json(lang):
    translations = _load_translations(lang)
    if translations is None:
        translations = _load_translations("zh-CN") or {}
    en_dict = _load_translations("en") or {}
    merged = dict(en_dict)
    merged.update(translations)
    return merged
