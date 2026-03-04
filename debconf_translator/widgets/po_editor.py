"""Inline PO file editor widget."""

import gettext
import re

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib, Pango

_ = gettext.gettext


class POEntry:
    """A single msgid/msgstr pair."""
    def __init__(self, msgid: str = "", msgstr: str = "", comments: str = "",
                 fuzzy: bool = False, context: str = ""):
        self.msgid = msgid
        self.msgstr = msgstr
        self.comments = comments
        self.fuzzy = fuzzy
        self.context = context


def parse_po(content: str) -> list[POEntry]:
    """Parse PO file content into entries."""
    entries = []
    current = POEntry()
    target = "msgid"

    for line in content.split("\n"):
        line = line.strip()

        if line.startswith("#"):
            if "fuzzy" in line:
                current.fuzzy = True
            current.comments += line + "\n"
        elif line.startswith("msgctxt "):
            current.context = _extract_string(line)
        elif line.startswith("msgid "):
            if current.msgid:  # Save previous
                entries.append(current)
                current = POEntry()
            current.msgid = _extract_string(line)
            target = "msgid"
        elif line.startswith("msgstr "):
            current.msgstr = _extract_string(line)
            target = "msgstr"
        elif line.startswith('"'):
            val = _extract_string(line)
            if target == "msgid":
                current.msgid += val
            else:
                current.msgstr += val
        elif not line:
            if current.msgid:
                entries.append(current)
                current = POEntry()
            target = "msgid"

    if current.msgid:
        entries.append(current)

    return entries


def entries_to_po(entries: list[POEntry], header: str = "") -> str:
    """Serialize entries back to PO format."""
    lines = []
    if header:
        lines.append(header)
        lines.append("")

    for entry in entries:
        if entry.comments:
            lines.append(entry.comments.rstrip())
        if entry.fuzzy:
            lines.append("#, fuzzy")
        if entry.context:
            lines.append(f'msgctxt "{_escape(entry.context)}"')
        lines.append(f'msgid "{_escape(entry.msgid)}"')
        lines.append(f'msgstr "{_escape(entry.msgstr)}"')
        lines.append("")

    return "\n".join(lines)


def _extract_string(line: str) -> str:
    m = re.search(r'"(.*)"', line)
    return m.group(1).replace("\\n", "\n").replace('\\"', '"') if m else ""


def _escape(s: str) -> str:
    return s.replace('"', '\\"').replace("\n", "\\n")


class POEditorWidget(Gtk.Box):
    """Widget for editing PO file entries inline."""

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self._entries: list[POEntry] = []
        self._rows: list[dict] = []
        self._modified = False

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(8)
        toolbar.set_margin_bottom(4)

        self._stats_label = Gtk.Label(label="")
        self._stats_label.add_css_class("dim-label")
        self._stats_label.set_halign(Gtk.Align.START)
        self._stats_label.set_hexpand(True)
        toolbar.append(self._stats_label)

        # Filter
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._filter_combo = Gtk.DropDown.new_from_strings([
            _("All"), _("Untranslated"), _("Fuzzy"), _("Translated")
        ])
        self._filter_combo.set_selected(0)
        self._filter_combo.connect("notify::selected", self._on_filter_changed)
        filter_box.append(Gtk.Label(label=_("Show:")))
        filter_box.append(self._filter_combo)
        toolbar.append(filter_box)

        self.append(toolbar)

        # Scrolled list of entries
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self._list_box)
        scrolled.set_vexpand(True)
        scrolled.set_margin_start(8)
        scrolled.set_margin_end(8)
        scrolled.set_margin_bottom(8)
        self.append(scrolled)

    def load_entries(self, entries: list[POEntry]):
        """Load PO entries into the editor."""
        self._entries = entries
        self._rebuild_list()

    def _rebuild_list(self):
        """Rebuild the entry list."""
        # Clear
        while row := self._list_box.get_first_child():
            self._list_box.remove(row)
        self._rows = []

        filter_idx = self._filter_combo.get_selected()

        translated = 0
        fuzzy = 0
        total = len(self._entries)

        for i, entry in enumerate(self._entries):
            if entry.msgid == "":  # Skip header
                continue

            has_translation = bool(entry.msgstr.strip())
            if has_translation:
                translated += 1
            if entry.fuzzy:
                fuzzy += 1

            # Apply filter
            if filter_idx == 1 and has_translation:
                continue
            if filter_idx == 2 and not entry.fuzzy:
                continue
            if filter_idx == 3 and not has_translation:
                continue

            row = self._create_entry_row(i, entry)
            self._list_box.append(row)

        self._stats_label.set_text(
            _("%(translated)d/%(total)d translated, %(fuzzy)d fuzzy") % {
                "translated": translated, "total": total - 1, "fuzzy": fuzzy
            }
        )

    def _create_entry_row(self, idx: int, entry: POEntry) -> Gtk.ListBoxRow:
        """Create a row for a PO entry."""
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        # Comment (if any)
        if entry.comments.strip():
            comment = Gtk.Label(label=entry.comments.strip())
            comment.add_css_class("dim-label")
            comment.set_halign(Gtk.Align.START)
            comment.set_wrap(True)
            comment.set_xalign(0)
            box.append(comment)

        # Source string (msgid)
        source_label = Gtk.Label(label=_("Source:"))
        source_label.add_css_class("heading")
        source_label.set_halign(Gtk.Align.START)
        box.append(source_label)

        msgid_label = Gtk.Label(label=entry.msgid)
        msgid_label.set_halign(Gtk.Align.START)
        msgid_label.set_wrap(True)
        msgid_label.set_xalign(0)
        msgid_label.set_selectable(True)
        box.append(msgid_label)

        # Translation (msgstr) - editable
        trans_label = Gtk.Label(label=_("Translation:"))
        trans_label.add_css_class("heading")
        trans_label.set_halign(Gtk.Align.START)
        trans_label.set_margin_top(4)
        box.append(trans_label)

        text_view = Gtk.TextView()
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.get_buffer().set_text(entry.msgstr)
        text_view.set_top_margin(4)
        text_view.set_bottom_margin(4)
        text_view.set_left_margin(8)
        text_view.set_right_margin(8)
        text_view.add_css_class("card")

        # Track changes
        text_view.get_buffer().connect("changed", self._on_text_changed, idx)

        frame = Gtk.Frame()
        frame.set_child(text_view)
        box.append(frame)

        # Fuzzy checkbox
        fuzzy_check = Gtk.CheckButton(label=_("Fuzzy"))
        fuzzy_check.set_active(entry.fuzzy)
        fuzzy_check.connect("toggled", self._on_fuzzy_toggled, idx)
        fuzzy_check.set_margin_top(4)
        box.append(fuzzy_check)

        row.set_child(box)
        self._rows.append({"row": row, "text_view": text_view, "fuzzy": fuzzy_check})
        return row

    def _on_text_changed(self, buffer, idx):
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        self._entries[idx].msgstr = buffer.get_text(start, end, False)
        self._modified = True

    def _on_fuzzy_toggled(self, check, idx):
        self._entries[idx].fuzzy = check.get_active()
        self._modified = True

    def _on_filter_changed(self, *_args):
        self._rebuild_list()

    def get_entries(self) -> list[POEntry]:
        return self._entries

    @property
    def modified(self) -> bool:
        return self._modified
