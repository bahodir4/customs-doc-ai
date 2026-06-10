"""Application configuration package.

Import `settings` from this module anywhere in the codebase.
Never read environment variables directly elsewhere.
"""
from config.settings import AppSettings, get_settings, settings

__all__ = ["AppSettings", "get_settings", "settings"]
