import json
import threading
from copy import deepcopy
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
STATE_PATH = DATA_DIR / "state.json"

DEFAULT_STATE = {
    "media_roots": {
        "primary": "/srv/vframe-media",
        "secondary": "/mnt/vframe-media",
    },
    "storage": {
        "overflow_threshold_gb": 10,
    },
    "settings": {
        "slide_duration": 12.0,
        "transition": "fade",
        "transition_duration": 0.6,
        "shuffle": True,
        "mute": False,
        "fit_mode": "fit-blur",
        "display_width": 1024,
        "display_height": 600,
    },
    "albums": [],
    "current_album_id": None,
}


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _default_state():
    return deepcopy(DEFAULT_STATE)


def _load_state_from_disk():
    if not STATE_PATH.exists():
        return _default_state()
    try:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return _default_state()
    for key, value in DEFAULT_STATE.items():
        if key not in data:
            data[key] = deepcopy(value)
    if "media_roots" not in data or not isinstance(data["media_roots"], dict):
        legacy = data.get("media_root")
        data["media_roots"] = deepcopy(DEFAULT_STATE["media_roots"])
        if legacy:
            data["media_roots"]["primary"] = legacy
    if "settings" not in data or not isinstance(data["settings"], dict):
        data["settings"] = deepcopy(DEFAULT_STATE["settings"])
    else:
        for key, value in DEFAULT_STATE["settings"].items():
            if key not in data["settings"]:
                data["settings"][key] = value
    if "storage" not in data or not isinstance(data["storage"], dict):
        data["storage"] = deepcopy(DEFAULT_STATE["storage"])
    else:
        for key, value in DEFAULT_STATE["storage"].items():
            if key not in data["storage"]:
                data["storage"][key] = value
    if "albums" not in data or not isinstance(data["albums"], list):
        data["albums"] = []
    return data


def _save_state_to_disk(state):
    _ensure_dirs()
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


class StateStore:
    def __init__(self):
        _ensure_dirs()
        self._lock = threading.Lock()
        self._state = _load_state_from_disk()
        _save_state_to_disk(self._state)

    def get_state(self):
        with self._lock:
            return deepcopy(self._state)

    def save_state(self, state):
        with self._lock:
            self._state = deepcopy(state)
            _save_state_to_disk(self._state)

    def update_state(self, updater):
        with self._lock:
            state = deepcopy(self._state)
            state = updater(state)
            self._state = deepcopy(state)
            _save_state_to_disk(self._state)
            return deepcopy(self._state)

    def resolve_media_roots(self, state=None):
        if state is None:
            state = self.get_state()
        media_roots = state.get("media_roots", DEFAULT_STATE["media_roots"])
        resolved = {}
        for name, root in media_roots.items():
            media_path = Path(root)
            if not media_path.is_absolute():
                media_path = ROOT_DIR / media_path
            try:
                media_path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                pass
            resolved[name] = media_path
        return resolved
