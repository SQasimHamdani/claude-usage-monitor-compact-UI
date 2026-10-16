"""
Account Switching (Linux)
============================

No-op: multi-account switching is backed by the Windows-only
``claudeswitch`` package (DPAPI-encrypted profile storage, Win32 atomic
file replace, ``psutil``-based session detection).  No Linux-native
equivalent exists yet - see ``accounts_win32.py``.
"""
from __future__ import annotations

from typing import Any

__all__ = ['SwitcherService', 'accounts_supported', 'build_accounts_menu', 'start_usage_cache_refresh']


class SwitcherService:
    """No-op stand-in - multi-account switching is not available on Linux."""

    def __init__(self, notify: Any = None, on_change: Any = None) -> None:
        pass

    def start_background_sync(self, interval_s: float = 300.0) -> None:
        pass

    def stop(self) -> None:
        pass


def accounts_supported() -> bool:
    """Whether multi-account switching is available on this platform."""
    return False


def build_accounts_menu(switcher: SwitcherService, translations: dict[str, Any]) -> None:
    """Return None - the caller omits the menu entirely when unsupported."""
    return None


def start_usage_cache_refresh(switcher: SwitcherService, interval_s: float = 90.0) -> Any:
    """Return a no-op stop callable - there is no cache to keep warm on Linux."""
    return lambda: None
