"""Standalone QSwitch GUI."""

__version__ = "0.1.0"
from .controller import Actor, PermissionDeniedError, PermissionMode, QSwitchController

__all__ = ["Actor", "PermissionDeniedError", "PermissionMode", "QSwitchController"]
