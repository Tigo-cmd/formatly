"""Formatly engine: check and correct documents against a rulebook."""

from .engine import CheckResult, FixResult, check, fix
from .rulebook import Rulebook, load_rulebook, rulebook_from_dict

__version__ = "0.1.0"
__all__ = ["CheckResult", "FixResult", "Rulebook", "check", "fix", "load_rulebook", "rulebook_from_dict"]
