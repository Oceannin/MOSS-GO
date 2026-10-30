"""Curated character vocabulary and reviewed, portable presets."""

import json
from pathlib import Path
import random

from .errors import StudioError

_CATALOG = json.loads((Path(__file__).parent / "assets" / "character_catalog.json").read_text("utf-8"))
CHARACTER_FIELDS = {key: {"label": field["label"], "label_ru": field["label_ru"], "group": field["group"],
                          "values": [option[0] for option in field["options"]], "labels_ru": dict(field["options"])}
                    for key, field in _CATALOG["fields"].items()}
CHARACTER_PRESETS = _CATALOG["presets"]


def validate_character(data):
    if not isinstance(data, dict) or set(data) - CHARACTER_FIELDS.keys():
        raise StudioError("The character preset contains unsupported fields.", field="character")
    result = {}
    for key, value in data.items():
        if value not in CHARACTER_FIELDS[key]["values"]:
            raise StudioError("Choose a character trait from the catalog.", field="character")
        result[key] = value
    return result


def render_character(data):
    values = validate_character(data)
    return ", ".join(values[key] for key in CHARACTER_FIELDS if key in values)


def compose_prompt(description, character):
    """Attach canonical traits without repeating ones already present in the scene."""
    values = validate_character(character)
    present = description.casefold()
    missing = [values[key] for key in CHARACTER_FIELDS if key in values and values[key].casefold() not in present]
    return "\n".join(filter(None, [description, ", ".join(missing)]))


def random_character(seed, locks=None, *, fields=None):
    locks = validate_character(locks or {})
    if fields is None:
        fields = list(CHARACTER_FIELDS)
    if not isinstance(fields, list) or len(fields) > len(CHARACTER_FIELDS) or any(not isinstance(key, str) or key not in CHARACTER_FIELDS for key in fields):
        raise StudioError("Choose known character fields to randomize.", field="fields")
    rng = random.Random(seed)
    chosen = set(fields) | set(locks)
    return {key: locks[key] if key in locks else rng.choice(field["values"])
            for key, field in CHARACTER_FIELDS.items() if key in chosen}


def import_character(data):
    """Return a clean preview; unsupported legacy data is never executed or retained."""
    if not isinstance(data, dict):
        raise StudioError("Expected a character preset.")
    values = data.get("character", data)
    if not isinstance(values, dict):
        raise StudioError("Expected character traits.")
    clean = {key: value for key, value in values.items() if key in CHARACTER_FIELDS and value in CHARACTER_FIELDS[key]["values"]}
    removed = set(values) - set(clean)
    locks = []
    if "character" in data:
        if "format" in data and data["format"] != "moss-go-character":
            raise StudioError("This is not a MOSS GO character preset.")
        if "version" in data and (type(data["version"]) is not int or data["version"] != 1):
            raise StudioError("This character preset version is not supported.")
        removed.update("metadata." + key for key in set(data) - {"character", "locks", "format", "version"})
        source_locks = data.get("locks", [])
        if not isinstance(source_locks, list) or len(source_locks) > 128:
            raise StudioError("Preset pins must be a list of character fields.")
        for key in source_locks:
            if isinstance(key, str) and key in clean:
                if key not in locks:
                    locks.append(key)
            else:
                removed.add("locks." + (key if isinstance(key, str) else "invalid"))
    return {"character": clean, "locks": locks, "removed_fields": sorted(removed), "requires_review": bool(removed)}
