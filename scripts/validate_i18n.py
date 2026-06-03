import json
import os
import sys

def validate_i18n():
    locales_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bin", "integrated_app", "locales")
    if not os.path.isdir(locales_dir):
        print(f"Locales directory not found: {locales_dir}")
        sys.exit(1)
    langs = [f.replace(".json", "") for f in os.listdir(locales_dir) if f.endswith(".json")]
    if not langs:
        print("No locale files found.")
        sys.exit(1)
    all_keys = {}
    for lang in langs:
        with open(os.path.join(locales_dir, f"{lang}.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        keys = set(_flatten_keys(data))
        all_keys[lang] = keys
        print(f"[{lang}] {len(keys)} keys")
    reference = all_keys.get("zh", set())
    has_error = False
    for lang in langs:
        if lang == "zh":
            continue
        missing = reference - all_keys[lang]
        extra = all_keys[lang] - reference
        if missing:
            print(f"[{lang}] Missing keys: {sorted(missing)}")
            has_error = True
        if extra:
            print(f"[{lang}] Extra keys: {sorted(extra)}")
    if not has_error:
        print("All locale files are consistent.")
    print("Validation complete.")

def _flatten_keys(data, prefix=""):
    keys = []
    for k, v in data.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full_key))
        else:
            keys.append(full_key)
    return keys

if __name__ == "__main__":
    validate_i18n()
