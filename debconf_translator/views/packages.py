from .. import _
"""Package browser and translation view."""

import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib, Gio

from ..scraper import fetch_language_status, fetch_pot_file
from ..models import DebconfPackage
from ..widgets.po_editor import POEditorWidget, POEntry, parse_po, entries_to_po


DATA_DIR = Path(GLib.get_user_data_dir()) / "debconf-translator"


class PackagesView(Gtk.Box):
    """Browse packages and translate debconf templates."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window
        self._packages: list[DebconfPackage] = []

        # Language selector + search
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(16)
        toolbar.set_margin_end(16)
        toolbar.set_margin_top(12)

        toolbar.append(Gtk.Label(label=_("Language:")))
        self._lang_entry = Gtk.Entry()
        from ..app import load_config
        self._lang_entry.set_text(load_config().get("lang_code", "sv"))
        self._lang_entry.set_max_width_chars(6)
        self._lang_entry.set_width_chars(6)
        toolbar.append(self._lang_entry)

        # Sort dropdown
        toolbar.append(Gtk.Label(label=_("Sort:")))
        self._sort_combo = Gtk.DropDown.new_from_strings([
            _("Strings ↓"), _("A-Z"), _("Strings ↑")
        ])
        self._sort_combo.set_selected(0)
        self._sort_combo.connect("notify::selected", self._on_sort_changed)
        toolbar.append(self._sort_combo)

        fetch_btn = Gtk.Button(label=_("Fetch Packages"))
        fetch_btn.add_css_class("suggested-action")
        fetch_btn.connect("clicked", self._on_fetch)
        toolbar.append(fetch_btn)

        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(_("Filter packages…"))
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_search_changed)
        toolbar.append(self._search)

        self.append(toolbar)

        # Status
        self._status = Gtk.Label(label="")
        self._status.add_css_class("dim-label")
        self._status.set_margin_start(16)
        self._status.set_margin_top(4)
        self._status.set_halign(Gtk.Align.START)
        self.append(self._status)

        # Split: package list left, editor right
        self._paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._paned.set_position(350)
        self._paned.set_vexpand(True)
        self._paned.set_margin_start(16)
        self._paned.set_margin_end(16)
        self._paned.set_margin_top(8)
        self._paned.set_margin_bottom(16)

        # Package list
        self._pkg_list = Gtk.ListBox()
        self._pkg_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._pkg_list.add_css_class("boxed-list")
        self._pkg_list.connect("row-selected", self._on_package_selected)
        self._pkg_list.set_filter_func(self._filter_func)

        pkg_scroll = Gtk.ScrolledWindow()
        pkg_scroll.set_child(self._pkg_list)
        pkg_scroll.set_min_content_width(300)
        self._paned.set_start_child(pkg_scroll)

        # Editor placeholder
        self._editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        placeholder = Adw.StatusPage()
        placeholder.set_icon_name("document-edit-symbolic")
        placeholder.set_title(_("Select a Package"))
        placeholder.set_description(_("Choose a package from the list to start translating"))
        self._editor_box.append(placeholder)

        editor_scroll = Gtk.ScrolledWindow()
        editor_scroll.set_child(self._editor_box)
        self._paned.set_end_child(editor_scroll)

        self.append(self._paned)

    def _on_fetch(self, _btn):
        lang = self._lang_entry.get_text().strip()
        if not lang:
            return

        self._status.set_text(_("Fetching packages for %s…") % lang)

        def do_fetch():
            stats, pkgs, _ = fetch_language_status(lang)
            GLib.idle_add(self._populate_packages, stats, pkgs)

        threading.Thread(target=do_fetch, daemon=True).start()

    def _on_sort_changed(self, *_args):
        if self._packages:
            self._populate_packages(None, self._packages, resort_only=True)

    def _populate_packages(self, stats, packages, resort_only=False):
        while row := self._pkg_list.get_first_child():
            self._pkg_list.remove(row)
        if not resort_only:
            self._packages = packages

        sort_idx = self._sort_combo.get_selected()
        if sort_idx == 0:  # Strings descending
            packages.sort(key=lambda p: p.strings_total, reverse=True)
        elif sort_idx == 1:  # Alphabetical
            packages.sort(key=lambda p: p.name)
        elif sort_idx == 2:  # Strings ascending
            packages.sort(key=lambda p: p.strings_total)

        for pkg in packages:
            row = Adw.ActionRow()
            row.set_title(pkg.name)
            row.set_subtitle(_("%d strings") % pkg.strings_total)
            row.add_prefix(Gtk.Image.new_from_icon_name("package-x-generic-symbolic"))
            row.pkg = pkg
            self._pkg_list.append(row)

        if stats:
            self._status.set_text(
                _("%(translated)d/%(total)d strings — %(pkgs)d untranslated packages") % {
                    "translated": stats.translated,
                    "total": stats.total,
                    "pkgs": len(packages),
                }
            )

    def _on_package_selected(self, _listbox, row):
        if row is None or not hasattr(row, "pkg"):
            return
        pkg = row.pkg
        self._load_package_pot(pkg)

    def _load_package_pot(self, pkg: DebconfPackage):
        """Load or download the POT file for editing."""
        # Clear editor
        while child := self._editor_box.get_first_child():
            self._editor_box.remove(child)

        spinner = Gtk.Spinner()
        spinner.start()
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.set_valign(Gtk.Align.CENTER)
        spinner.set_vexpand(True)
        self._editor_box.append(spinner)

        def do_load():
            # Check local file first
            local_dir = DATA_DIR / "translations"
            local_dir.mkdir(parents=True, exist_ok=True)
            local_po = local_dir / f"{pkg.name}.po"

            if local_po.exists():
                content = local_po.read_text()
            else:
                content = fetch_pot_file(pkg.name)
                if content:
                    local_po.write_text(content)

            GLib.idle_add(self._show_editor, pkg, content)

        threading.Thread(target=do_load, daemon=True).start()

    def _show_editor(self, pkg, content):
        while child := self._editor_box.get_first_child():
            self._editor_box.remove(child)

        if not content:
            status = Adw.StatusPage()
            status.set_icon_name("dialog-error-symbolic")
            status.set_title(_("Could Not Load Template"))
            status.set_description(_("Failed to download the POT file for %s") % pkg.name)
            self._editor_box.append(status)
            return

        # Toolbar for this package
        pkg_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pkg_toolbar.set_margin_start(8)
        pkg_toolbar.set_margin_end(8)
        pkg_toolbar.set_margin_top(8)

        pkg_label = Gtk.Label(label=pkg.name)
        pkg_label.add_css_class("title-3")
        pkg_label.set_hexpand(True)
        pkg_label.set_halign(Gtk.Align.START)
        pkg_toolbar.append(pkg_label)

        save_btn = Gtk.Button(label=_("Save"))
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save, pkg)
        pkg_toolbar.append(save_btn)

        export_btn = Gtk.Button(label=_("Export .po"))
        export_btn.connect("clicked", self._on_export, pkg)
        pkg_toolbar.append(export_btn)

        self._editor_box.append(pkg_toolbar)

        # PO editor
        entries = parse_po(content)
        editor = POEditorWidget()
        editor.load_entries(entries)
        editor.set_vexpand(True)
        self._editor_box.append(editor)
        self._current_editor = editor
        self._current_pkg = pkg

    def _on_save(self, _btn, pkg):
        entries = self._current_editor.get_entries()
        content = entries_to_po(entries)
        local_dir = DATA_DIR / "translations"
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / f"{pkg.name}.po").write_text(content)
        self._status.set_text(_("Saved %s") % pkg.name)

    def _on_export(self, _btn, pkg):
        entries = self._current_editor.get_entries()
        content = entries_to_po(entries)

        dialog = Gtk.FileDialog()
        dialog.set_initial_name(f"{pkg.name}.sv.po")
        dialog.save(self.window, None, self._on_export_done, content)

    def _on_export_done(self, dialog, result, content):
        try:
            gfile = dialog.save_finish(result)
            path = gfile.get_path()
            Path(path).write_text(content)
            self._status.set_text(_("Exported to %s") % path)
        except Exception:
            pass

    def _on_search_changed(self, entry):
        self._pkg_list.invalidate_filter()

    def _filter_func(self, row):
        query = self._search.get_text().lower()
        if not query:
            return True
        if hasattr(row, "pkg"):
            return query in row.pkg.name.lower()
        return True

    def open_package(self, pkg: DebconfPackage):
        """Open a specific package for editing (called from dashboard)."""
        self._load_package_pot(pkg)
