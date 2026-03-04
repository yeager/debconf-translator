from . import _
"""Data models for debconf translation tracking."""

import json
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from pathlib import Path
from typing import Optional


class TranslationStatus(IntEnum):
    UNTRANSLATED = 0
    IN_PROGRESS = 1
    TRANSLATED = 2
    SUBMITTED = 3  # Sent to BTS


@dataclass
class DebconfPackage:
    """A Debian package with debconf templates."""
    name: str
    section: str = "main"
    strings_total: int = 0
    strings_translated: int = 0
    popcon_rank: int = 0
    status: TranslationStatus = TranslationStatus.UNTRANSLATED
    pot_url: str = ""
    po_path: str = ""  # Local path to .po file
    bts_bug: str = ""  # Bug number if submitted
    notes: str = ""

    @property
    def progress(self) -> float:
        if self.strings_total == 0:
            return 0.0
        return self.strings_translated / self.strings_total * 100

    @property
    def display_status(self) -> str:
        return {
            TranslationStatus.UNTRANSLATED: _("Untranslated"),
            TranslationStatus.IN_PROGRESS: _("In Progress"),
            TranslationStatus.TRANSLATED: _("Translated"),
            TranslationStatus.SUBMITTED: _("Submitted"),
        }.get(self.status, "?")


@dataclass
class ReviewItem:
    """A debconf template under review on l10n.debian.org."""
    package: str
    status: str = ""  # "bts", "review", etc.
    bug_number: str = ""
    reviewer: str = ""
    date: str = ""
    original_strings: list = field(default_factory=list)
    new_strings: list = field(default_factory=list)
    url: str = ""


@dataclass
class LanguageStats:
    """Statistics for a language."""
    code: str
    name: str
    translated: int = 0
    total: int = 0
    untranslated_packages: int = 0
    in_progress_packages: int = 0

    @property
    def progress(self) -> float:
        if self.total == 0:
            return 0.0
        return self.translated / self.total * 100


