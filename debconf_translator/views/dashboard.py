"""Dashboard view showing translation statistics and translator rankings."""

import gettext
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

from ..scraper import fetch_language_status, DEBIAN_LANGUAGES, TranslatorStats
from ..models import LanguageStats

_ = gettext.gettext


class DashboardView(Gtk.Box):
    """Overview dashboard with language statistics and top translators."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window

        # Title bar
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.set_margin_start(24)
        title_box.set_margin_top(16)
        title_box.set_margin_end(24)

        title = Gtk.Label(label=_("Translation Overview"))
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        title_box.append(title)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text(_("Refresh All Statistics"))
        refresh_btn.connect("clicked", lambda _: self.refresh())
        title_box.append(refresh_btn)

        self.append(title_box)

        # Spinner + status
        self._spinner = Gtk.Spinner()
        self._spinner.set_margin_top(8)
        self._spinner.set_halign(Gtk.Align.CENTER)
        self.append(self._spinner)

        self._status_label = Gtk.Label(label=_("Click refresh to load statistics"))
        self._status_label.add_css_class("dim-label")
        self._status_label.set_margin_top(4)
        self._status_label.set_margin_start(24)
        self._status_label.set_halign(Gtk.Align.START)
        self.append(self._status_label)

        # Main content: scrollable
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_margin_start(24)
        scrolled.set_margin_end(24)
        scrolled.set_margin_top(12)
        scrolled.set_margin_bottom(16)

        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        scrolled.set_child(self._content_box)
        self.append(scrolled)

    def refresh(self):
        """Fetch stats for multiple languages."""
        self._spinner.start()
        self._status_label.set_text(_("Fetching statistics for multiple languages…"))

        # Clear content
        while child := self._content_box.get_first_child():
            self._content_box.remove(child)

        def do_fetch():
            results = []
            sv_translators = []

            # Fetch a selection of popular languages
            priority_langs = ["sv", "da", "de", "fr", "es", "it", "nl", "pl", "pt_BR", "nb", "fi", "ru", "ja", "cs", "zh_CN"]

            for lang_code in priority_langs:
                try:
                    stats, pkgs, translators = fetch_language_status(lang_code)
                    lang_name = dict(DEBIAN_LANGUAGES).get(lang_code, lang_code)
                    stats.name = lang_name
                    results.append((stats, len(pkgs)))
                    if lang_code == "sv":
                        sv_translators = translators
                except Exception:
                    pass

            GLib.idle_add(self._on_all_stats_loaded, results, sv_translators)

        threading.Thread(target=do_fetch, daemon=True).start()

    def _on_all_stats_loaded(self, results, sv_translators):
        self._spinner.stop()

        # Clear
        while child := self._content_box.get_first_child():
            self._content_box.remove(child)

        if not results:
            self._status_label.set_text(_("Failed to fetch statistics"))
            return

        self._status_label.set_text(
            _("Loaded statistics for %d languages") % len(results)
        )

        # --- Language Statistics ---
        lang_group = Adw.PreferencesGroup()
        lang_group.set_title(_("Language Statistics"))
        lang_group.set_description(_("Translation progress across languages (sorted by completion)"))

        # Sort by progress
        results.sort(key=lambda r: r[0].progress, reverse=True)

        for stats, untranslated_pkgs in results:
            row = Adw.ActionRow()
            row.set_title(f"{stats.name} ({stats.code})")
            pct = stats.progress
            row.set_subtitle(
                _("%(translated)d/%(total)d strings (%(pct).1f%%) — %(pkgs)d untranslated packages") % {
                    "translated": stats.translated,
                    "total": stats.total,
                    "pct": pct,
                    "pkgs": untranslated_pkgs,
                }
            )

            # Flag/icon
            row.add_prefix(Gtk.Image.new_from_icon_name("preferences-desktop-locale-symbolic"))

            # Progress bar
            progress = Gtk.ProgressBar()
            progress.set_fraction(pct / 100.0)
            progress.set_valign(Gtk.Align.CENTER)
            progress.set_size_request(120, -1)
            if pct >= 95:
                progress.add_css_class("success")
            elif pct >= 70:
                progress.add_css_class("accent")
            else:
                progress.add_css_class("warning")
            row.add_suffix(progress)

            # Percentage label
            pct_label = Gtk.Label(label=f"{pct:.0f}%")
            pct_label.add_css_class("heading")
            pct_label.set_width_chars(5)
            row.add_suffix(pct_label)

            row.stats = stats
            lang_group.add(row)

        self._content_box.append(lang_group)

        # --- Top Translators (Swedish) ---
        if sv_translators:
            trans_group = Adw.PreferencesGroup()
            trans_group.set_title(_("🏆 Top Translators — Swedish"))
            trans_group.set_description(
                _("Ranked by total translated strings in debconf templates")
            )

            medals = ["🥇", "🥈", "🥉"]
            for i, t in enumerate(sv_translators[:15]):
                row = Adw.ActionRow()
                medal = medals[i] if i < 3 else f"#{i + 1}"
                row.set_title(f"{medal} {t.name}")
                row.set_subtitle(
                    _("%(pkgs)d packages — %(strings)d strings") % {
                        "pkgs": t.packages,
                        "strings": t.strings,
                    }
                )
                row.add_prefix(Gtk.Image.new_from_icon_name("avatar-default-symbolic"))

                # String count badge
                badge = Gtk.Label(label=str(t.strings))
                badge.add_css_class("accent")
                badge.add_css_class("heading")
                row.add_suffix(badge)

                trans_group.add(row)

            self._content_box.append(trans_group)

        # --- Untranslated packages for Swedish ---
        sv_result = next((r for r in results if r[0].code == "sv"), None)
        if sv_result and sv_result[1] > 0:
            info_label = Gtk.Label(
                label=_("💡 Go to the Packages tab to start translating untranslated Swedish packages.")
            )
            info_label.add_css_class("dim-label")
            info_label.set_wrap(True)
            info_label.set_halign(Gtk.Align.START)
            self._content_box.append(info_label)
