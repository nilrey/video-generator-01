# scenes_loader.py
"""Загрузчик и валидатор content/scenes.json + presets/*.json."""
from __future__ import annotations
import json
from pathlib import Path
from copy import deepcopy

REQUIRED = ("key", "ill", "title", "tag", "text")
OPTIONAL = ("type_index", "color", "voice", "ill_params")

PRESET_SECTIONS = ("caption", "title", "illustration", "audio", "timing", "colors")


def load_scenes(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"scenes.json not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))

    scenes = raw.get("scenes")
    if not scenes or not isinstance(scenes, list):
        raise ValueError("scenes.json: 'scenes' must be a non-empty list")

    meta = dict(raw.get("meta", {}))

    seen = set()
    for i, s in enumerate(scenes):
        miss = [k for k in REQUIRED if k not in s]
        if miss:
            raise ValueError(f"scene[{i}] ({s.get('key', '?')}): missing {miss}")
        if s["key"] in seen:
            raise ValueError(f"duplicate scene key: {s['key']}")
        seen.add(s["key"])

        s.setdefault("type_index", None)
        s.setdefault("color", [124, 92, 255])
        s.setdefault("voice", s["key"])
        s.setdefault("ill_params", {})

        if not isinstance(s["color"], (list, tuple)) or len(s["color"]) != 3:
            raise ValueError(f"scene '{s['key']}': color must be [r,g,b]")
        s["color"] = tuple(int(c) for c in s["color"])

    if "types_count" not in meta:
        meta["types_count"] = sum(1 for s in scenes if s.get("type_index") is not None)

    meta.setdefault("output_name", "short.mp4")
    meta.setdefault("speech_rate", 1.0)

    style_name = raw.get("style", "default_style")
    style_path = p.parent / "presets" / f"{style_name}.json"

    return {
        "meta": meta,
        "style": style_name,
        "style_path": style_path,
        "scenes": scenes,
    }


def load_preset(path):
    """Читает presets/*.json. Если файла нет — пустой пресет (все дефолты).
    Отсутствующие секции/ключи не ломают apply_style: остаются дефолты из shorts_creator."""
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for k in PRESET_SECTIONS:
        if k in raw and isinstance(raw[k], dict):
            out[k] = dict(raw[k])
    return out


def clone(data):
    return deepcopy(data)