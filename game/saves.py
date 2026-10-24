"""
Character persistence.

One JSON file per character at data/saves/<name>.json. The character name IS the file name,
so names are restricted to 1-12 lowercase letters (a-z) and must be unique.

Schema:
{
  "name": "heskan", "class_name": "Wizard",
  "level": 16, "xp": 367, "gold": 112440, "kills": 757,
  "quests": {                       # quest progression is per character AND per map
    "northshire": {
      "completed": ["quest_id", ...],
      "active": ["quest_id", ...],
      "progress": {"quest_id": {"Monster Name": kills_so_far}}
    }
  }
}
Pure logic (no pygame) so it can be unit tested.
"""
import json
import os
import re

SAVE_DIR = os.path.join("data", "saves")
MAX_NAME_LEN = 12
_NAME_RE = re.compile(r"^[a-z]{1,%d}$" % MAX_NAME_LEN)
# Names that are reserved device names on Windows and so can't be used as file names.
_RESERVED = {"con", "prn", "aux", "nul"}


def _path(name, save_dir=None):
    return os.path.join(save_dir or SAVE_DIR, f"{name}.json")


def validate_name(name, save_dir=None):
    """Return an error message, or None if `name` is acceptable for a NEW character."""
    if not name:
        return "Enter a name"
    if not _NAME_RE.match(name):
        return f"Name must be 1-{MAX_NAME_LEN} lowercase letters (a-z)"
    if name in _RESERVED:
        return "That name is reserved"
    if os.path.exists(_path(name, save_dir)):
        return "A character with that name already exists"
    return None


def blank_character(name, class_name):
    return {
        "name": name, "class_name": class_name,
        "level": 1, "xp": 0, "gold": 0, "kills": 0,
        "quests": {},
    }


def _migrate(data, name):
    """Upgrade older save formats in place. Returns True if anything changed."""
    changed = False
    if data.get("name") != name:
        data["name"] = name  # legacy saves used a capitalised display name
        changed = True
    if "quests" not in data:
        # Legacy: quest state was global but only Northshire had quests.
        completed = data.pop("completed_quests", [])
        active = data.pop("active_quests", None)
        if active is None:
            cur = data.pop("current_quest_id", None)
            active = [cur] if cur else []
        data["quests"] = {"northshire": {"completed": completed, "active": active, "progress": {}}}
        changed = True
    for key, default in (("level", 1), ("xp", 0), ("gold", 0), ("kills", 0)):
        if key not in data:
            data[key] = default
            changed = True
    return changed


def load_character(name, save_dir=None):
    """Load (and migrate) one character. Returns the data dict, or None if missing/corrupt."""
    path = _path(name, save_dir)
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[SAVE] Could not read {path}: {e}")
        return None
    if _migrate(data, name):
        save_character(data, save_dir)
    return data


def save_character(data, save_dir=None):
    """Atomically write a character file."""
    d = save_dir or SAVE_DIR
    os.makedirs(d, exist_ok=True)
    path = _path(data["name"], d)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def list_characters(save_dir=None):
    """All saved characters, sorted by name."""
    d = save_dir or SAVE_DIR
    if not os.path.isdir(d):
        return []
    chars = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        name = fn[:-5]
        if not _NAME_RE.match(name.lower()):
            continue
        data = load_character(name, d)
        if data and data.get("class_name"):
            chars.append(data)
    return chars


def create_character(name, class_name, save_dir=None):
    """Validate and create a new level-1 character. Returns (data, error)."""
    err = validate_name(name, save_dir)
    if err:
        return None, err
    data = blank_character(name, class_name)
    save_character(data, save_dir)
    return data, None


def delete_character(name, save_dir=None):
    """Permanently delete a character. Returns True if a file was removed."""
    try:
        os.remove(_path(name, save_dir))
        return True
    except OSError:
        return False
