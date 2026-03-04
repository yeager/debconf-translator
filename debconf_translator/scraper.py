"""Scrape debconf translation status from debian.org."""

import gettext
import logging
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from typing import Optional

from .models import DebconfPackage, LanguageStats, ReviewItem

_ = gettext.gettext
log = logging.getLogger(__name__)

BASE_URL = "https://www.debian.org/international/l10n/po-debconf"
REVIEW_URL = "https://l10n.debian.org/coordination/english/en.by_status.html"
POT_BASE = "https://www.debian.org/international/l10n/po-debconf/pot"


class _StatusParser(HTMLParser):
    """Parse the debconf l10n status page for a language."""

    def __init__(self):
        super().__init__()
        self.packages: list[DebconfPackage] = []
        self.stats = LanguageStats(code="", name="")
        self._in_section = ""
        self._in_link = False
        self._current_pkg = ""
        self._buffer = ""
        self._capture = False

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "a" and "href" in attrs_d:
            href = attrs_d["href"]
            if href.startswith("pot#"):
                self._current_pkg = href.replace("pot#", "")
                self._in_link = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            self._in_link = False

    def handle_data(self, data):
        # Parse stats line: "4999 strings are translated"
        m = re.search(r'(\d+)\s+strings are translated.*?from\s+(\d+)', data)
        if m:
            self.stats.translated = int(m.group(1))
            self.stats.total = int(m.group(2))

        # Parse string counts after package names: (5), (16), etc.
        if self._current_pkg:
            m2 = re.search(r'\((\d+)\)', data)
            if m2:
                pkg = DebconfPackage(
                    name=self._current_pkg,
                    strings_total=int(m2.group(1)),
                    pot_url=f"{POT_BASE}#{self._current_pkg}",
                )
                self.packages.append(pkg)
                self._current_pkg = ""

        # Section headers
        if "translation is to do" in data:
            self._in_section = "todo"
        elif "translation is underway" in data:
            self._in_section = "underway"
        elif "translation is uptodate" in data:
            self._in_section = "done"


class _ReviewParser(HTMLParser):
    """Parse the l10n.debian.org review status page."""

    def __init__(self):
        super().__init__()
        self.reviews: list[ReviewItem] = []
        self._in_row = False
        self._cells: list[str] = []
        self._in_cell = False
        self._cell_data = ""
        self._in_table = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._cells = []
        elif tag == "td" and self._in_row:
            self._in_cell = True
            self._cell_data = ""

    def handle_endtag(self, tag):
        if tag == "td" and self._in_cell:
            self._in_cell = False
            self._cells.append(self._cell_data.strip())
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if len(self._cells) >= 3:
                review = ReviewItem(
                    package=self._cells[0] if self._cells else "",
                    status=self._cells[1] if len(self._cells) > 1 else "",
                    bug_number=self._cells[2] if len(self._cells) > 2 else "",
                )
                if review.package:
                    self.reviews.append(review)
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data):
        if self._in_cell:
            self._cell_data += data


def fetch_language_status(lang_code: str) -> tuple[LanguageStats, list[DebconfPackage]]:
    """Fetch translation status for a language from debian.org."""
    url = f"{BASE_URL}/{lang_code}"
    log.info("Fetching %s", url)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DebconfTranslator/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        log.error("Failed to fetch %s: %s", url, e)
        return LanguageStats(code=lang_code, name=lang_code), []

    parser = _StatusParser()
    parser.feed(html)

    stats = parser.stats
    stats.code = lang_code
    stats.untranslated_packages = len(parser.packages)

    return stats, parser.packages


def fetch_pot_file(package_name: str) -> Optional[str]:
    """Download the .pot file for a package."""
    url = f"https://www.debian.org/international/l10n/po-debconf/pot/{package_name}"
    # The actual pot files are linked from the page
    # Try common patterns
    for suffix in [f"{package_name}.pot", f"templates.pot"]:
        try_url = f"https://www.debian.org/international/l10n/po-debconf/pot/{suffix}"
        try:
            req = urllib.request.Request(try_url, headers={"User-Agent": "DebconfTranslator/0.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError:
            continue
    return None


def fetch_reviews() -> list[ReviewItem]:
    """Fetch current review status from l10n.debian.org."""
    try:
        req = urllib.request.Request(REVIEW_URL, headers={"User-Agent": "DebconfTranslator/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        log.error("Failed to fetch reviews: %s", e)
        return []

    parser = _ReviewParser()
    parser.feed(html)
    return parser.reviews


# Common Debian languages
DEBIAN_LANGUAGES = [
    ("sv", "Swedish"), ("da", "Danish"), ("de", "German"),
    ("es", "Spanish"), ("fi", "Finnish"), ("fr", "French"),
    ("it", "Italian"), ("ja", "Japanese"), ("ko", "Korean"),
    ("nb", "Norwegian Bokmål"), ("nl", "Dutch"), ("pl", "Polish"),
    ("pt_BR", "Brazilian Portuguese"), ("ru", "Russian"),
    ("zh_CN", "Simplified Chinese"), ("cs", "Czech"),
    ("hu", "Hungarian"), ("ro", "Romanian"), ("vi", "Vietnamese"),
    ("uk", "Ukrainian"),
]
