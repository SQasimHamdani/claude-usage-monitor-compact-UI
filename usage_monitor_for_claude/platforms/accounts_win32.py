"""
Account Switching (Windows)
=============================

Thin wrapper around the third-party ``claudeswitch`` package, which owns
the encrypted profile store, the atomic live-file swap and the
session-running guard for switching between several Claude Code accounts.

This module adds two things claudeswitch's own ``tray`` helpers don't
cover: per-profile 5-hour/7-day usage in the menu labels, and a background
refresh that keeps that usage data warm without the menu ever blocking on
a network call.

``SwitcherService.profiles(with_usage=True)`` does a real, synchronous
fetch (cached 60s by claudeswitch itself) - calling it from the menu's own
item-list callback would make a right-click visibly stall whenever that
cache is cold.  claudeswitch already has the right tool for a non-blocking
read instead: ``claudeswitch.statusline`` shows the active profile's usage
by reading a cache file (``usage_cache``) that ``usage.write_cache_file()``
writes, tolerating up to 15 minutes of staleness rather than fetching live.
This module follows the same pattern: a periodic background thread keeps
that cache file fresh, and the menu only ever reads it.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from claudeswitch import fsutil  # type: ignore[import-untyped]
from claudeswitch.tray import SwitcherService  # type: ignore[import-untyped]

__all__ = ['SwitcherService', 'accounts_supported', 'build_accounts_menu', 'start_usage_cache_refresh']

# How long a cached usage reading is still shown in the menu, matching
# claudeswitch.statusline's own staleness tolerance for consistency.
_CACHE_STALE_AFTER_S = 900
# How often the background thread refreshes that cache - frequent enough
# that it is rarely stale by the time someone opens the menu, without
# hammering the API (usage.py also caches each fetch for 60s on its own).
_REFRESH_INTERVAL_S = 90.0


def accounts_supported() -> bool:
    """Whether multi-account switching is available on this platform."""
    return True


def start_usage_cache_refresh(switcher: SwitcherService, interval_s: float = _REFRESH_INTERVAL_S) -> Any:
    """Start a background thread that keeps claudeswitch's usage cache warm.

    Parameters
    ----------
    switcher : SwitcherService
        The running switcher service.
    interval_s : float
        Seconds between refreshes.

    Returns
    -------
    Callable[[], None]
        Call to stop the thread (e.g. on app quit).
    """
    stop_event = threading.Event()

    def loop() -> None:
        while not stop_event.wait(interval_s):
            try:
                switcher.profiles(with_usage=True)
            except Exception:
                # A transient failure (network, locked store) must not end
                # the refresh loop - the next tick retries on its own.
                continue

    threading.Thread(target=loop, name='claudeswitch-usage-cache', daemon=True).start()
    return stop_event.set


def _cached_usage(switcher: SwitcherService, key: str) -> dict[str, float] | None:
    """Return ``{'five_hour': pct, 'seven_day': pct}`` for *key* from the usage cache.

    None when no reading is cached yet, or the cached one is older than
    ``_CACHE_STALE_AFTER_S``.  Never touches the network.
    """
    cache = fsutil.read_json_or_none(switcher.store.paths.usage_cache) or {}
    entry = cache.get(key)
    if not entry or time.time() - entry.get('at', 0) >= _CACHE_STALE_AFTER_S:
        return None

    five_hour = entry.get('five_hour')
    seven_day = entry.get('seven_day')
    if five_hour is None or seven_day is None:
        return None

    return {'five_hour': five_hour, 'seven_day': seven_day}


def _plan_label(switcher: SwitcherService, key: str) -> str | None:
    """Return the saved profile's subscription plan (e.g. ``'Pro'``), or None.

    Already captured by claudeswitch into the non-secret ``store.json`` at
    save/sync time (``oauth_block(creds).get('subscriptionType')``), just
    not exposed through ``ProfileView`` - read directly instead of asking
    claudeswitch to add a field for a single display string.
    """
    profile = switcher.store.load().get('profiles', {}).get(key)
    plan = profile.get('subscription') if isinstance(profile, dict) else None
    return plan.title() if isinstance(plan, str) and plan else None


def _switch_handler(switcher: SwitcherService, key: str) -> Any:
    """Return a pystray click handler that switches to the given saved profile."""
    def handler(icon: Any, item: Any) -> None:
        switcher.switch_or_queue(key)
    return handler


def _active_flag(is_active: bool) -> Any:
    """Return a pystray ``checked`` callable with the given fixed value."""
    def checked(item: Any) -> bool:
        return is_active
    return checked


def build_accounts_menu(switcher: SwitcherService, translations: dict[str, Any]) -> Any:
    """Build the "Claude Accounts" pystray submenu, with each profile's quick usage.

    Parameters
    ----------
    switcher : SwitcherService
        The running switcher service.
    translations : dict
        The app's loaded translation dict (``i18n.T``).
    """
    import pystray  # local import: the Linux counterpart must not need it

    def items() -> Any:
        pending = switcher.pending_target
        for view in switcher.profiles():
            label = f'{view.name}  ({view.email})' if view.email else view.name
            plan = _plan_label(switcher, view.key)
            if plan:
                label += f'  [{plan}]'
            usage = _cached_usage(switcher, view.key)
            if usage:
                label += f"  · 5h {usage['five_hour']:.0f}% / 7d {usage['seven_day']:.0f}%"
            if view.needs_reauth:
                label += f"  [{translations['accounts_needs_login']}]"
            if pending == view.key:
                label += f"  [{translations['accounts_switching']}]"
            yield pystray.MenuItem(
                label, _switch_handler(switcher, view.key),
                checked=_active_flag(view.active), radio=True,
            )
        yield pystray.Menu.SEPARATOR
        if pending:
            yield pystray.MenuItem(
                translations['accounts_cancel_pending'].format(name=pending),
                lambda icon, item: (switcher.cancel_pending(), switcher.on_change()),
            )
        yield pystray.MenuItem(translations['accounts_add'], lambda icon, item: switcher.add_account())

    return pystray.MenuItem(translations['menu_accounts'], pystray.Menu(items))
