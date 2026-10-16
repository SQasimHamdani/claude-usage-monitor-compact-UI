"""
Account Switching Dispatch
=============================

Selects the multi-account switching backend for the running system.

Kept out of :mod:`usage_monitor_for_claude.platforms` for the same reason
as the popup host and single-instance guard: the Windows backend reaches
into the third-party ``claudeswitch`` package (and transitively
``psutil``), which the platform package itself must stay free of.
"""
from __future__ import annotations

import sys

if sys.platform == 'win32':
    from .accounts_win32 import SwitcherService, accounts_supported, build_accounts_menu, start_usage_cache_refresh
else:
    from .accounts_linux import SwitcherService, accounts_supported, build_accounts_menu, start_usage_cache_refresh

__all__ = ['SwitcherService', 'accounts_supported', 'build_accounts_menu', 'start_usage_cache_refresh']
