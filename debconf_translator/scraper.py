"""Scrape debconf translation status from debian.org."""

import gettext
import gzip
import logging
import re
import urllib.request
import urllib.error
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional

from .models import DebconfPackage, LanguageStats, ReviewItem

_ = gettext.gettext
log = logging.getLogger(__name__)

BASE_URL = "https://www.debian.org/international/l10n/po-debconf"
REVIEW_URL = "https://l10n.debian.org/coordination/english/en.by_status.html"
POT_BASE = "https://www.debian.org/international/l10n/po-debconf/pot"


@dataclass
class TranslatorStats:
    """Statistics for a single translator."""
    name: str
    packages: int = 0
    strings: int = 0


class _StatusParser(HTMLParser):
    """Parse the debconf l10n status page for a language."""

    def __init__(self):
        super().__init__()
        self.packages: list[DebconfPackage] = []
        self.stats = LanguageStats(code="", name="")
        self.translators: dict[str, TranslatorStats] = {}
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
                    pot_url="",  # Will be resolved from POT index
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


def fetch_language_status(lang_code: str) -> tuple[LanguageStats, list[DebconfPackage], list[TranslatorStats]]:
    """Fetch translation status for a language from debian.org.

    Returns (stats, untranslated_packages, translator_rankings).
    """
    url = f"{BASE_URL}/{lang_code}"
    log.info("Fetching %s", url)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DebconfTranslator/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        log.error("Failed to fetch %s: %s", url, e)
        return LanguageStats(code=lang_code, name=lang_code), [], []

    parser = _StatusParser()
    parser.feed(html)

    stats = parser.stats
    stats.code = lang_code
    stats.untranslated_packages = len(parser.packages)

    # Regex fallback for stats (HTMLParser misses multi-node text)
    m = re.search(r'(\d+)\s+strings are translated.*?from\s+(\d+)', html, re.DOTALL)
    if m and stats.translated == 0:
        stats.translated = int(m.group(1))
        stats.total = int(m.group(2))

    # Parse translator stats from 'done' table rows
    # Pattern: <td>SCORE (Nt;Nf;Nu)</td>...<td>TRANSLATOR_NAME</td>
    translators: dict[str, TranslatorStats] = {}
    for m in re.finditer(
        r'<td>\s*(\d+)%\s*\((\d+)t;\d+f;\d+u\)</td>'
        r'.*?<td>([^<]+)</td>\s*</tr>',
        html, re.DOTALL
    ):
        _pct, str_count, name = m.group(1), int(m.group(2)), m.group(3).strip()
        # Decode HTML entities
        name = name.replace("&#197;", "Å").replace("&#228;", "ä").replace("&#246;", "ö")
        name = re.sub(r'&#\d+;', '', name).strip()
        if name and name != "Translator":
            if name not in translators:
                translators[name] = TranslatorStats(name=name)
            translators[name].packages += 1
            translators[name].strings += str_count

    # Sort by strings translated (descending)
    ranked = sorted(translators.values(), key=lambda t: t.strings, reverse=True)

    return stats, parser.packages, ranked


_pot_url_cache: dict[str, str] = {}


def _build_pot_url_index() -> dict[str, str]:
    """Scrape the POT index page to map package names to .pot.gz URLs."""
    if _pot_url_cache:
        return _pot_url_cache

    url = f"{POT_BASE}"
    log.info("Building POT URL index from %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DebconfTranslator/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        log.error("Failed to fetch POT index: %s", e)
        return {}

    # Pattern: <a name="PKGNAME" ...>...</a> [<a href="URL">templates.pot</a>]
    # Match each package anchor followed by its pot.gz link
    for m in re.finditer(
        r'<a\s+name="([^"]+)"[^>]*>.*?'
        r'<a\s+href="(https://i18n\.debian\.org/[^"]*\.pot\.gz)"',
        html, re.DOTALL
    ):
        pkg_name = m.group(1)
        pot_gz_url = m.group(2)
        _pot_url_cache[pkg_name] = pot_gz_url

    log.info("Indexed %d POT URLs", len(_pot_url_cache))
    return _pot_url_cache


def fetch_pot_file(package_name: str) -> Optional[str]:
    """Download the .pot file for a package from i18n.debian.org."""
    index = _build_pot_url_index()
    pot_gz_url = index.get(package_name)

    if not pot_gz_url:
        log.warning("No POT URL found for %s", package_name)
        return None

    log.info("Downloading %s", pot_gz_url)
    try:
        req = urllib.request.Request(pot_gz_url, headers={"User-Agent": "DebconfTranslator/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            gz_data = resp.read()
            return gzip.decompress(gz_data).decode("utf-8", errors="replace")
    except (urllib.error.URLError, gzip.BadGzipFile, OSError) as e:
        log.error("Failed to download POT for %s: %s", package_name, e)
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
