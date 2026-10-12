import threading

_lock = threading.Lock()
_modes: dict[int, str] = {}

DEFAULT_MODE = "direct"
VALID_MODES = {"direct", "mihomo", "personal"}


def get_mode(user_id: int) -> str:
    with _lock:
        return _modes.get(user_id, DEFAULT_MODE)


def set_mode(user_id: int, mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"Неизвестный режим: {mode}")
    with _lock:
        _modes[user_id] = mode


def reset_mode(user_id: int) -> None:
    with _lock:
        _modes.pop(user_id, None)
