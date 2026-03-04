"""BTS submission view — generate and submit translation bugs."""

import gettext
import subprocess
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

_ = gettext.gettext

DATA_DIR = Path(GLib.get_user_data_dir()) / "debconf-translator"


class SubmitView(Gtk.Box):
    """View for submitting translations to Debian BTS."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window

        # Title
        title = Gtk.Label(label=_("Submit Translations"))
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        title.set_margin_start(24)
        title.set_margin_top(16)
        self.append(title)

        desc = Gtk.Label(
            label=_("Submit completed translations to the Debian Bug Tracking System (BTS).")
        )
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        desc.set_halign(Gtk.Align.START)
        desc.set_margin_start(24)
        desc.set_margin_top(4)
        self.append(desc)

        # Translator info
        info_group = Adw.PreferencesGroup()
        info_group.set_title(_("Translator Information"))
        info_group.set_margin_start(24)
        info_group.set_margin_end(24)
        info_group.set_margin_top(16)

        self._name_row = Adw.EntryRow()
        self._name_row.set_title(_("Full Name"))
        info_group.add(self._name_row)

        self._email_row = Adw.EntryRow()
        self._email_row.set_title(_("Email"))
        info_group.add(self._email_row)

        self._lang_row = Adw.EntryRow()
        self._lang_row.set_title(_("Language Code"))
        self._lang_row.set_text("sv")
        info_group.add(self._lang_row)

        self.append(info_group)

        # Saved translations list
        trans_group = Adw.PreferencesGroup()
        trans_group.set_title(_("Saved Translations"))
        trans_group.set_description(_("Translations ready to submit"))
        trans_group.set_margin_start(24)
        trans_group.set_margin_end(24)
        trans_group.set_margin_top(16)

        self._trans_list = Gtk.ListBox()
        self._trans_list.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self._trans_list.add_css_class("boxed-list")
        trans_group.add(self._trans_list)

        refresh_btn = Gtk.Button(label=_("Refresh List"))
        refresh_btn.connect("clicked", self._refresh_translations)
        trans_group.add(refresh_btn)

        self.append(trans_group)

        # Submit actions
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_start(24)
        action_box.set_margin_end(24)
        action_box.set_margin_top(16)
        action_box.set_margin_bottom(16)

        preview_btn = Gtk.Button(label=_("Preview Email"))
        preview_btn.connect("clicked", self._on_preview)
        action_box.append(preview_btn)

        submit_btn = Gtk.Button(label=_("Generate Bug Report"))
        submit_btn.add_css_class("suggested-action")
        submit_btn.connect("clicked", self._on_submit)
        action_box.append(submit_btn)

        self.append(action_box)

        # Preview area
        self._preview_frame = Gtk.Frame()
        self._preview_frame.set_margin_start(24)
        self._preview_frame.set_margin_end(24)
        self._preview_frame.set_margin_bottom(16)

        self._preview_text = Gtk.TextView()
        self._preview_text.set_editable(False)
        self._preview_text.set_wrap_mode(Gtk.WrapMode.WORD)
        self._preview_text.set_monospace(True)
        self._preview_text.set_top_margin(8)
        self._preview_text.set_bottom_margin(8)
        self._preview_text.set_left_margin(8)
        self._preview_text.set_right_margin(8)
        self._preview_frame.set_child(self._preview_text)
        self.append(self._preview_frame)

    def _refresh_translations(self, _btn=None):
        """List saved .po files."""
        while row := self._trans_list.get_first_child():
            self._trans_list.remove(row)

        trans_dir = DATA_DIR / "translations"
        if not trans_dir.exists():
            return

        for po_file in sorted(trans_dir.glob("*.po")):
            row = Adw.ActionRow()
            row.set_title(po_file.stem)
            row.set_subtitle(str(po_file))
            row.add_prefix(Gtk.Image.new_from_icon_name("document-edit-symbolic"))

            check = Gtk.CheckButton()
            check.set_valign(Gtk.Align.CENTER)
            row.add_suffix(check)
            row.po_path = po_file
            row.check = check
            self._trans_list.append(row)

    def _get_selected_files(self) -> list[Path]:
        files = []
        row = self._trans_list.get_first_child()
        while row:
            if hasattr(row, "check") and row.check.get_active():
                files.append(row.po_path)
            row = row.get_next_sibling()
        return files

    def _generate_bug_text(self, pkg_name: str, po_path: Path) -> str:
        """Generate a BTS bug report email."""
        name = self._name_row.get_text()
        email = self._email_row.get_text()
        lang = self._lang_row.get_text()

        po_content = po_path.read_text()

        return (
            f"Package: {pkg_name}\n"
            f"Severity: wishlist\n"
            f"Tags: l10n patch\n\n"
            f"Please include the attached {lang}.po file as\n"
            f"debian/po/{lang}.po in the next upload of {pkg_name}.\n\n"
            f"The translation is for the debconf templates.\n\n"
            f"Translator: {name} <{email}>\n"
            f"Language: {lang}\n\n"
            f"---\n{po_content}"
        )

    def _on_preview(self, _btn):
        files = self._get_selected_files()
        if not files:
            self._preview_text.get_buffer().set_text(_("No translations selected."))
            return

        text = ""
        for f in files:
            text += self._generate_bug_text(f.stem, f)
            text += "\n\n" + "=" * 60 + "\n\n"

        self._preview_text.get_buffer().set_text(text)

    def _on_submit(self, _btn):
        files = self._get_selected_files()
        if not files:
            return

        # Export to a directory for manual submission
        export_dir = DATA_DIR / "bugs"
        export_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            text = self._generate_bug_text(f.stem, f)
            out = export_dir / f"{f.stem}-bug.txt"
            out.write_text(text)

        dialog = Adw.AlertDialog.new(
            _("Bug Reports Generated"),
            _("Reports saved to:\n%s\n\nUse 'reportbug' or email submit@bugs.debian.org") % str(export_dir)
        )
        dialog.add_response("ok", _("OK"))
        dialog.present(self.window)
