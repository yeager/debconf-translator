"""GTK4/Adwaita application entry point."""

import gettext
import json
import locale
import logging
import os
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from . import __app_id__, __version__

# Set up locale and gettext
try:
    locale.bindtextdomain('debconf-translator', '/usr/share/locale')
    locale.textdomain('debconf-translator')
except AttributeError:
    pass  # macOS lacks locale.bindtextdomain
gettext.bindtextdomain('debconf-translator', '/usr/share/locale')
gettext.textdomain('debconf-translator')
_ = gettext.gettext
log = logging.getLogger(__name__)

CONFIG_DIR = Path(GLib.get_user_config_dir()) / "debconf-translator"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


class DebconfTranslatorApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.config = load_config()
        self._setup_actions()

    def _setup_actions(self):
        actions = [
            ("quit", self._on_quit, ["<primary>q"]),
            ("about", self._on_about, None),
            ("shortcuts", self._on_shortcuts, ["<primary>question"]),
            ("theme", self._on_toggle_theme, ["<primary>t"]),
        ]
        for name, callback, accels in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)

        self.set_accels_for_action("win.navigate-dashboard", ["<primary>1"])
        self.set_accels_for_action("win.navigate-packages", ["<primary>2"])
        self.set_accels_for_action("win.navigate-reviews", ["<primary>3"])
        self.set_accels_for_action("win.navigate-submit", ["<primary>4"])

    def do_activate(self):
        from .window import DebconfTranslatorWindow

        win = self.props.active_window
        if not win:
            win = DebconfTranslatorWindow(application=self)

        if not self.config.get("first_run_done"):
            self._show_welcome(win)
            self.config["first_run_done"] = True
            save_config(self.config)

        win.present()

    def _show_welcome(self, parent):
        dialog = Adw.AlertDialog.new(
            _("Welcome to Debconf Translation Manager"),
            _(
                "Translate Debian package configuration dialogs.\n\n"
                "• Browse untranslated debconf templates\n"
                "• Edit translations with the built-in PO editor\n"
                "• Track review status from l10n.debian.org\n"
                "• Generate BTS bug reports for submission"
            ),
        )
        dialog.add_response("ok", _("Get Started"))
        dialog.set_default_response("ok")
        dialog.present(parent)

    def _on_quit(self, *_args):
        self.quit()

    def _on_about(self, *_args):
        win = self.props.active_window
        about = Adw.AboutDialog.new()
        about.set_application_name(_("Debconf Translation Manager"))
        about.set_application_icon(__app_id__)
        about.set_version(__version__)
        about.set_developer_name("Daniel Nylander")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://github.com/yeager/debconf-translator")
        about.set_issue_url("https://github.com/yeager/debconf-translator/issues")
        about.set_developers(["Daniel Nylander <daniel@danielnylander.se>"])
        about.set_copyright("© 2026 Daniel Nylander")
        about.set_comments(
            _("GTK4/Adwaita tool for managing Debconf template translations")
        )

        debug_lines = [
            f"debconf-translator {__version__}",
            f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
            f"libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}",
            f"Python {sys.version}",
            f"OS: {os.uname().sysname} {os.uname().release}",
        ]
        about.set_debug_info("\n".join(debug_lines))
        about.set_debug_info_filename("debconf-translator-debug.txt")
        about.present(win)

    def _on_shortcuts(self, *_args):
        win = self.props.active_window
        builder = Gtk.Builder.new_from_string(SHORTCUTS_UI, -1)
        shortcuts_win = builder.get_object("shortcuts")
        shortcuts_win.set_transient_for(win)
        shortcuts_win.present()

    def _on_toggle_theme(self, *_args):
        sm = Adw.StyleManager.get_default()
        if sm.get_dark():
            sm.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            sm.set_color_scheme(Adw.ColorScheme.FORCE_DARK)


SHORTCUTS_UI = """\
<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <object class="GtkShortcutsWindow" id="shortcuts">
    <property name="modal">1</property>
    <child>
      <object class="GtkShortcutsSection">
        <property name="section-name">shortcuts</property>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title" translatable="yes">General</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes">Toggle Dark Theme</property>
                <property name="accelerator">&lt;primary&gt;t</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes">Keyboard Shortcuts</property>
                <property name="accelerator">&lt;primary&gt;question</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes">Quit</property>
                <property name="accelerator">&lt;primary&gt;q</property>
              </object>
            </child>
          </object>
        </child>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title" translatable="yes">Navigation</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes">Dashboard</property>
                <property name="accelerator">&lt;primary&gt;1</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes">Packages</property>
                <property name="accelerator">&lt;primary&gt;2</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes">Review Board</property>
                <property name="accelerator">&lt;primary&gt;3</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes">Submit</property>
                <property name="accelerator">&lt;primary&gt;4</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
  </object>
</interface>
"""


def main():
    app = DebconfTranslatorApp()
    return app.run(sys.argv)
