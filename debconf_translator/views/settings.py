"""Settings view — all preferences in one place."""
from .. import _

import locale
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ..app import load_config, save_config
from ..scraper import DEBIAN_LANGUAGES


class SettingsView(Gtk.Box):
    """All settings consolidated into sidebar settings button."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window
        self._config = load_config()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scrolled.set_child(content)
        self.append(scrolled)

        title = Gtk.Label(label=_("Settings"))
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        title.set_margin_start(24)
        title.set_margin_top(16)
        content.append(title)

        # --- Language ---
        lang_group = Adw.PreferencesGroup()
        lang_group.set_title(_("Language"))
        lang_group.set_margin_start(24)
        lang_group.set_margin_end(24)
        lang_group.set_margin_top(16)

        # Auto-detect from LANG
        system_lang = self._detect_system_lang()

        self._lang_row = Adw.ComboRow()
        self._lang_row.set_title(_("Translation Language"))
        self._lang_row.set_subtitle(_("Language you translate into"))
        lang_names = [f"{name} ({code})" for code, name in DEBIAN_LANGUAGES]
        self._lang_row.set_model(Gtk.StringList.new(lang_names))

        # Select current language
        saved_lang = self._config.get("lang_code", system_lang)
        for i, (code, _name) in enumerate(DEBIAN_LANGUAGES):
            if code == saved_lang:
                self._lang_row.set_selected(i)
                break
        self._lang_row.connect("notify::selected", self._on_setting_changed)
        lang_group.add(self._lang_row)

        content.append(lang_group)

        # --- Translator Info ---
        info_group = Adw.PreferencesGroup()
        info_group.set_title(_("Translator"))
        info_group.set_margin_start(24)
        info_group.set_margin_end(24)
        info_group.set_margin_top(16)

        self._name_row = Adw.EntryRow()
        self._name_row.set_title(_("Full Name"))
        self._name_row.set_text(self._config.get("translator_name", ""))
        self._name_row.connect("changed", self._on_setting_changed)
        info_group.add(self._name_row)

        self._email_row = Adw.EntryRow()
        self._email_row.set_title(_("Email"))
        self._email_row.set_text(self._config.get("email", ""))
        self._email_row.connect("changed", self._on_setting_changed)
        info_group.add(self._email_row)

        content.append(info_group)

        # --- SMTP ---
        smtp_group = Adw.PreferencesGroup()
        smtp_group.set_title(_("Email Sending"))
        smtp_group.set_description(_("Configure how to send bug reports to Debian BTS"))
        smtp_group.set_margin_start(24)
        smtp_group.set_margin_end(24)
        smtp_group.set_margin_top(16)

        self._method_row = Adw.ComboRow()
        self._method_row.set_title(_("Send Method"))
        methods = Gtk.StringList.new([
            _("Gmail (SMTP)"),
            _("Custom SMTP"),
            _("Export Only (no send)"),
        ])
        self._method_row.set_model(methods)
        method_map = {"gmail": 0, "smtp": 1, "export": 2}
        self._method_row.set_selected(method_map.get(self._config.get("smtp_method", "export"), 2))
        self._method_row.connect("notify::selected", self._on_setting_changed)
        smtp_group.add(self._method_row)

        self._smtp_server = Adw.EntryRow()
        self._smtp_server.set_title(_("SMTP Server"))
        self._smtp_server.set_text(self._config.get("smtp_server", "smtp.gmail.com"))
        self._smtp_server.connect("changed", self._on_setting_changed)
        smtp_group.add(self._smtp_server)

        self._smtp_port = Adw.SpinRow.new_with_range(25, 2525, 1)
        self._smtp_port.set_title(_("SMTP Port"))
        self._smtp_port.set_value(self._config.get("smtp_port", 587))
        self._smtp_port.connect("notify::value", self._on_setting_changed)
        smtp_group.add(self._smtp_port)

        self._password_row = Adw.PasswordEntryRow()
        self._password_row.set_title(_("Password / App Password"))
        smtp_group.add(self._password_row)

        content.append(smtp_group)

        # --- Display ---
        display_group = Adw.PreferencesGroup()
        display_group.set_title(_("Display"))
        display_group.set_margin_start(24)
        display_group.set_margin_end(24)
        display_group.set_margin_top(16)

        self._sort_row = Adw.ComboRow()
        self._sort_row.set_title(_("Default Package Sort"))
        sorts = Gtk.StringList.new([
            _("String Count (most first)"),
            _("Alphabetical"),
            _("Popcon Rank"),
        ])
        self._sort_row.set_model(sorts)
        self._sort_row.set_selected(self._config.get("sort_order", 0))
        self._sort_row.connect("notify::selected", self._on_setting_changed)
        display_group.add(self._sort_row)

        content.append(display_group)

        # --- Reset ---
        reset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        reset_box.set_halign(Gtk.Align.END)
        reset_box.set_margin_end(24)
        reset_box.set_margin_top(24)
        reset_box.set_margin_bottom(24)

        reset_btn = Gtk.Button(label=_("Reset to Defaults"))
        reset_btn.add_css_class("destructive-action")
        reset_btn.connect("clicked", self._on_reset)
        reset_box.append(reset_btn)
        content.append(reset_box)

    def _detect_system_lang(self) -> str:
        """Detect language from LANG environment variable."""
        lang = os.environ.get("LANG", "en_US.UTF-8")
        # Extract language code: sv_SE.UTF-8 -> sv
        code = lang.split("_")[0].split(".")[0]
        # Map to debian codes
        for dc, _ in DEBIAN_LANGUAGES:
            if dc == code or dc.startswith(code):
                return dc
        return "sv"

    def _on_setting_changed(self, *_args):
        """Save all settings."""
        method_values = ["gmail", "smtp", "export"]
        lang_codes = [code for code, _ in DEBIAN_LANGUAGES]

        self._config["lang_code"] = lang_codes[self._lang_row.get_selected()]
        self._config["translator_name"] = self._name_row.get_text()
        self._config["email"] = self._email_row.get_text()
        self._config["smtp_method"] = method_values[self._method_row.get_selected()]
        self._config["smtp_server"] = self._smtp_server.get_text()
        self._config["smtp_port"] = int(self._smtp_port.get_value())
        self._config["sort_order"] = self._sort_row.get_selected()
        save_config(self._config)

    def _on_reset(self, _btn):
        self._lang_row.set_selected(0)
        self._name_row.set_text("")
        self._email_row.set_text("")
        self._method_row.set_selected(2)
        self._smtp_server.set_text("smtp.gmail.com")
        self._smtp_port.set_value(587)
        self._sort_row.set_selected(0)

    def get_lang_code(self) -> str:
        lang_codes = [code for code, _ in DEBIAN_LANGUAGES]
        return lang_codes[self._lang_row.get_selected()]
