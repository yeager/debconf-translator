"""Dashboard view showing translation statistics."""

import gettext
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

from ..scraper import fetch_language_status, DEBIAN_LANGUAGES
from ..models import LanguageStats

_ = gettext.gettext


class DashboardView(Gtk.Box):
    """Overview dashboard with language statistics."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window
        self._stats: list[tuple[LanguageStats, int]] = []

        # Title
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
        refresh_btn.set_tooltip_text(_("Refresh Statistics"))
        refresh_btn.connect("clicked", lambda _: self.refresh())
        title_box.append(refresh_btn)

        self.append(title_box)

        # Spinner
        self._spinner = Gtk.Spinner()
        self._spinner.set_margin_top(32)
        self._spinner.set_halign(Gtk.Align.CENTER)
        self.append(self._spinner)

        # Status label
        self._status_label = Gtk.Label(label=_("Click refresh to load statistics"))
        self._status_label.add_css_class("dim-label")
        self._status_label.set_margin_top(8)
        self.append(self._status_label)

        # Language list
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.connect("row-selected", self._on_language_selected)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self._list_box)
        scrolled.set_vexpand(True)
        scrolled.set_margin_start(24)
        scrolled.set_margin_end(24)
        scrolled.set_margin_top(16)
        scrolled.set_margin_bottom(16)
        self.append(scrolled)

    def refresh(self):
        """Fetch stats for Swedish (primary language)."""
        self._spinner.start()
        self._status_label.set_text(_("Fetching statistics…"))

        def do_fetch():
            stats, packages = fetch_language_status("sv")
            GLib.idle_add(self._on_stats_loaded, stats, packages)

        threading.Thread(target=do_fetch, daemon=True).start()

    def _on_stats_loaded(self, stats, packages):
        self._spinner.stop()

        # Clear list
        while row := self._list_box.get_first_child():
            self._list_box.remove(row)

        pct = stats.progress
        self._status_label.set_text(
            _("Swedish: %(translated)d/%(total)d strings (%(pct).1f%%) — %(pkgs)d untranslated packages") % {
                "translated": stats.translated,
                "total": stats.total,
                "pct": pct,
                "pkgs": len(packages),
            }
        )

        # Group by string count (most strings first = most impact)
        packages.sort(key=lambda p: p.strings_total, reverse=True)

        for pkg in packages:
            row = Adw.ActionRow()
            row.set_title(pkg.name)
            row.set_subtitle(_("%(n)d strings — Section: %(section)s") % {
                "n": pkg.strings_total, "section": pkg.section
            })
            row.add_prefix(Gtk.Image.new_from_icon_name("package-x-generic-symbolic"))

            # String count badge
            badge = Gtk.Label(label=str(pkg.strings_total))
            badge.add_css_class("accent")
            badge.add_css_class("heading")
            row.add_suffix(badge)
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))

            row.pkg = pkg
            self._list_box.append(row)

    def _on_language_selected(self, listbox, row):
        if row is None or not hasattr(row, "pkg"):
            return
        if self.window and hasattr(self.window, "open_package_editor"):
            self.window.open_package_editor(row.pkg)
