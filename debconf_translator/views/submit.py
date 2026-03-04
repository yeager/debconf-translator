"""BTS submission view — generate and submit translation bugs via email."""

import email.mime.text
import email.mime.multipart
import email.mime.application
import gettext
import logging
import smtplib
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

from ..app import load_config, save_config

_ = gettext.gettext
log = logging.getLogger(__name__)

DATA_DIR = Path(GLib.get_user_data_dir()) / "debconf-translator"

# Debian BTS email
BTS_EMAIL = "submit@bugs.debian.org"


class SubmitView(Gtk.Box):
    """View for submitting translations to Debian BTS."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window
        self._config = load_config()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scrolled.set_child(content)
        self.append(scrolled)

        # Title
        title = Gtk.Label(label=_("Submit Translations"))
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        title.set_margin_start(24)
        title.set_margin_top(16)
        content.append(title)

        desc = Gtk.Label(
            label=_("Submit translations to the Debian Bug Tracking System via email.\n"
                     "Bug reports are sent to submit@bugs.debian.org with the .po file attached.")
        )
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        desc.set_halign(Gtk.Align.START)
        desc.set_margin_start(24)
        desc.set_margin_top(4)
        content.append(desc)

        # --- SMTP Settings ---
        smtp_group = Adw.PreferencesGroup()
        smtp_group.set_title(_("Email Settings"))
        smtp_group.set_description(_("Configure how to send bug reports"))
        smtp_group.set_margin_start(24)
        smtp_group.set_margin_end(24)
        smtp_group.set_margin_top(16)

        # SMTP method
        self._method_row = Adw.ComboRow()
        self._method_row.set_title(_("Send Method"))
        self._method_row.set_subtitle(_("How to deliver the bug report email"))
        methods = Gtk.StringList.new([
            _("Gmail (SMTP)"),
            _("Custom SMTP"),
            _("Export Only (no send)"),
        ])
        self._method_row.set_model(methods)
        method_map = {"gmail": 0, "smtp": 1, "export": 2}
        self._method_row.set_selected(method_map.get(self._config.get("smtp_method", "export"), 2))
        self._method_row.connect("notify::selected", self._on_smtp_method_changed)
        smtp_group.add(self._method_row)

        # Email address (from)
        self._email_row = Adw.EntryRow()
        self._email_row.set_title(_("Your Email"))
        self._email_row.set_text(self._config.get("email", ""))
        smtp_group.add(self._email_row)

        # Full name
        self._name_row = Adw.EntryRow()
        self._name_row.set_title(_("Full Name"))
        self._name_row.set_text(self._config.get("translator_name", ""))
        smtp_group.add(self._name_row)

        # SMTP server (for custom)
        self._smtp_server_row = Adw.EntryRow()
        self._smtp_server_row.set_title(_("SMTP Server"))
        self._smtp_server_row.set_text(self._config.get("smtp_server", "smtp.gmail.com"))
        smtp_group.add(self._smtp_server_row)

        # SMTP port
        self._smtp_port_row = Adw.SpinRow.new_with_range(25, 2525, 1)
        self._smtp_port_row.set_title(_("SMTP Port"))
        self._smtp_port_row.set_value(self._config.get("smtp_port", 587))
        smtp_group.add(self._smtp_port_row)

        # Password (app password for Gmail)
        self._password_row = Adw.PasswordEntryRow()
        self._password_row.set_title(_("Password / App Password"))
        smtp_group.add(self._password_row)

        # Language code
        self._lang_row = Adw.EntryRow()
        self._lang_row.set_title(_("Language Code"))
        self._lang_row.set_text(self._config.get("lang_code", "sv"))
        smtp_group.add(self._lang_row)

        # Save settings button
        save_btn = Gtk.Button(label=_("Save Settings"))
        save_btn.connect("clicked", self._on_save_settings)
        smtp_group.add(save_btn)

        content.append(smtp_group)

        # Gmail help
        gmail_info = Adw.PreferencesGroup()
        gmail_info.set_title(_("📧 Gmail Setup"))
        gmail_info.set_description(
            _("To use Gmail:\n"
              "1. Enable 2-factor authentication on your Google account\n"
              "2. Go to myaccount.google.com → Security → App passwords\n"
              "3. Generate an app password for 'Mail'\n"
              "4. Use that password here (not your regular Gmail password)")
        )
        gmail_info.set_margin_start(24)
        gmail_info.set_margin_end(24)
        gmail_info.set_margin_top(8)
        content.append(gmail_info)

        # --- Saved Translations ---
        trans_group = Adw.PreferencesGroup()
        trans_group.set_title(_("Saved Translations"))
        trans_group.set_description(_("Select translations to submit"))
        trans_group.set_margin_start(24)
        trans_group.set_margin_end(24)
        trans_group.set_margin_top(16)

        self._trans_list = Gtk.ListBox()
        self._trans_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._trans_list.add_css_class("boxed-list")
        trans_group.add(self._trans_list)

        refresh_btn = Gtk.Button(label=_("Refresh List"))
        refresh_btn.connect("clicked", self._refresh_translations)
        trans_group.add(refresh_btn)

        content.append(trans_group)

        # --- Actions ---
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_start(24)
        action_box.set_margin_end(24)
        action_box.set_margin_top(16)

        preview_btn = Gtk.Button(label=_("Preview Email"))
        preview_btn.connect("clicked", self._on_preview)
        action_box.append(preview_btn)

        export_btn = Gtk.Button(label=_("Export to File"))
        export_btn.connect("clicked", self._on_export)
        action_box.append(export_btn)

        send_btn = Gtk.Button(label=_("Send to BTS"))
        send_btn.add_css_class("suggested-action")
        send_btn.connect("clicked", self._on_send)
        action_box.append(send_btn)

        content.append(action_box)

        # Status
        self._status_label = Gtk.Label(label="")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_margin_start(24)
        self._status_label.set_margin_top(8)
        content.append(self._status_label)

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

        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_child(self._preview_text)
        preview_scroll.set_min_content_height(100)
        preview_scroll.set_max_content_height(300)
        self._preview_frame.set_child(preview_scroll)
        content.append(self._preview_frame)

        self._on_smtp_method_changed()

    def _on_smtp_method_changed(self, *_args):
        """Show/hide SMTP fields based on selected method."""
        idx = self._method_row.get_selected()
        is_custom = (idx == 1)
        is_export = (idx == 2)

        self._smtp_server_row.set_visible(is_custom)
        self._smtp_port_row.set_visible(not is_export)
        self._password_row.set_visible(not is_export)

        if idx == 0:  # Gmail
            self._smtp_server_row.set_text("smtp.gmail.com")
            self._smtp_port_row.set_value(587)

    def _on_save_settings(self, _btn):
        method_values = ["gmail", "smtp", "export"]
        self._config["smtp_method"] = method_values[self._method_row.get_selected()]
        self._config["email"] = self._email_row.get_text()
        self._config["translator_name"] = self._name_row.get_text()
        self._config["smtp_server"] = self._smtp_server_row.get_text()
        self._config["smtp_port"] = int(self._smtp_port_row.get_value())
        self._config["lang_code"] = self._lang_row.get_text()
        save_config(self._config)
        self._status_label.set_text(_("Settings saved"))

    def _refresh_translations(self, _btn=None):
        while row := self._trans_list.get_first_child():
            self._trans_list.remove(row)

        trans_dir = DATA_DIR / "translations"
        if not trans_dir.exists():
            self._status_label.set_text(_("No saved translations found"))
            return

        count = 0
        for po_file in sorted(trans_dir.glob("*.po")):
            row = Adw.ActionRow()
            row.set_title(po_file.stem)
            # Count translated strings
            content = po_file.read_text()
            import re
            total = len(re.findall(r'^msgid ', content, re.MULTILINE)) - 1
            translated = len(re.findall(r'^msgstr ".+"', content, re.MULTILINE))
            row.set_subtitle(_("%(translated)d/%(total)d strings") % {
                "translated": translated, "total": max(0, total)
            })
            row.add_prefix(Gtk.Image.new_from_icon_name("document-edit-symbolic"))

            check = Gtk.CheckButton()
            check.set_valign(Gtk.Align.CENTER)
            row.add_suffix(check)
            row.po_path = po_file
            row.check = check
            self._trans_list.append(row)
            count += 1

        self._status_label.set_text(_("%d translations found") % count)

    def _get_selected_files(self) -> list[Path]:
        files = []
        row = self._trans_list.get_first_child()
        while row:
            if hasattr(row, "check") and row.check.get_active():
                files.append(row.po_path)
            row = row.get_next_sibling()
        return files

    def _build_email(self, pkg_name: str, po_path: Path) -> email.mime.multipart.MIMEMultipart:
        """Build a proper BTS email with .po attachment."""
        name = self._name_row.get_text()
        sender = self._email_row.get_text()
        lang = self._lang_row.get_text()

        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = f"{name} <{sender}>"
        msg["To"] = BTS_EMAIL
        msg["Subject"] = f"{pkg_name}: [INTL:{lang}] Swedish translation of debconf templates"

        body = (
            f"Package: {pkg_name}\n"
            f"Severity: wishlist\n"
            f"Tags: l10n patch\n\n"
            f"Please include the attached translation for the debconf templates\n"
            f"as debian/po/{lang}.po in the next upload of {pkg_name}.\n\n"
            f"Translator: {name} <{sender}>\n"
            f"Language: {lang}\n"
        )
        msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

        # Attach .po file
        po_content = po_path.read_bytes()
        attachment = email.mime.application.MIMEApplication(po_content, Name=f"{lang}.po")
        attachment["Content-Disposition"] = f'attachment; filename="{lang}.po"'
        msg.attach(attachment)

        return msg

    def _on_preview(self, _btn):
        files = self._get_selected_files()
        if not files:
            self._preview_text.get_buffer().set_text(_("No translations selected."))
            return

        text = ""
        for f in files:
            msg = self._build_email(f.stem, f)
            text += f"To: {BTS_EMAIL}\n"
            text += f"Subject: {msg['Subject']}\n"
            text += f"From: {msg['From']}\n\n"
            # Show body part
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    text += part.get_payload(decode=True).decode()
            text += f"\n[Attachment: {f.stem}.po]\n"
            text += "\n" + "=" * 60 + "\n\n"

        self._preview_text.get_buffer().set_text(text)

    def _on_export(self, _btn):
        """Export bug reports to files."""
        files = self._get_selected_files()
        if not files:
            return

        export_dir = DATA_DIR / "bugs"
        export_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            msg = self._build_email(f.stem, f)
            out = export_dir / f"{f.stem}-bug.eml"
            out.write_text(msg.as_string())

        self._status_label.set_text(
            _("Exported %d bug reports to %s") % (len(files), str(export_dir))
        )

    def _on_send(self, _btn):
        """Send bug reports via SMTP."""
        files = self._get_selected_files()
        if not files:
            self._status_label.set_text(_("No translations selected"))
            return

        method_idx = self._method_row.get_selected()
        if method_idx == 2:  # Export only
            self._on_export(_btn)
            return

        sender = self._email_row.get_text()
        password = self._password_row.get_text()

        if not sender or not password:
            dialog = Adw.AlertDialog.new(
                _("Missing Credentials"),
                _("Please enter your email and password/app password.")
            )
            dialog.add_response("ok", _("OK"))
            dialog.present(self.window)
            return

        # Confirm
        dialog = Adw.AlertDialog.new(
            _("Send Bug Reports?"),
            _("This will send %d bug report(s) to submit@bugs.debian.org.\n\n"
              "Are you sure?") % len(files)
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("send", _("Send"))
        dialog.set_response_appearance("send", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_send_confirmed, files, sender, password)
        dialog.present(self.window)

    def _on_send_confirmed(self, dialog, response, files, sender, password):
        if response != "send":
            return

        method_idx = self._method_row.get_selected()
        if method_idx == 0:  # Gmail
            server = "smtp.gmail.com"
            port = 587
        else:  # Custom SMTP
            server = self._smtp_server_row.get_text()
            port = int(self._smtp_port_row.get_value())

        self._status_label.set_text(_("Sending…"))

        def do_send():
            results = []
            try:
                smtp = smtplib.SMTP(server, port, timeout=30)
                smtp.ehlo()
                smtp.starttls()
                smtp.login(sender, password)

                for f in files:
                    try:
                        msg = self._build_email(f.stem, f)
                        smtp.sendmail(sender, [BTS_EMAIL], msg.as_string())
                        results.append((f.stem, True, ""))
                    except Exception as e:
                        results.append((f.stem, False, str(e)))

                smtp.quit()
            except Exception as e:
                for f in files:
                    results.append((f.stem, False, str(e)))

            GLib.idle_add(self._on_send_done, results)

        threading.Thread(target=do_send, daemon=True).start()

    def _on_send_done(self, results):
        ok = sum(1 for _, success, _ in results if success)
        fail = sum(1 for _, success, _ in results if not success)

        if fail == 0:
            self._status_label.set_text(_("✅ Sent %d bug reports successfully!") % ok)
        else:
            errors = "\n".join(f"  {name}: {err}" for name, success, err in results if not success)
            self._status_label.set_text(
                _("Sent %(ok)d, failed %(fail)d") % {"ok": ok, "fail": fail}
            )
            dialog = Adw.AlertDialog.new(
                _("Some Submissions Failed"),
                errors
            )
            dialog.add_response("ok", _("OK"))
            dialog.present(self.window)
