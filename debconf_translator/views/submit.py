"""BTS submission view — submit translations to Debian BTS."""
from .. import _

import email.mime.text
import email.mime.multipart
import email.mime.application
import json
import logging
import smtplib
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

from ..app import load_config, save_config
from ..scraper import DEBIAN_LANGUAGES

log = logging.getLogger(__name__)

DATA_DIR = Path(GLib.get_user_data_dir()) / "debconf-translator"
BTS_EMAIL = "submit@bugs.debian.org"
SUBMITTED_FILE = DATA_DIR / "submitted.json"


def _load_submitted() -> dict:
    if SUBMITTED_FILE.exists():
        try:
            return json.loads(SUBMITTED_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_submitted(data: dict):
    SUBMITTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBMITTED_FILE.write_text(json.dumps(data, indent=2))


class SubmitView(Gtk.Box):
    """View for submitting translations to Debian BTS."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window

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
            label=_("Submit translations to the Debian Bug Tracking System.\n"
                     "Configure email settings in Settings (⚙) before sending.")
        )
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        desc.set_halign(Gtk.Align.START)
        desc.set_margin_start(24)
        desc.set_margin_top(4)
        content.append(desc)

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
        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_min_content_height(100)
        preview_scroll.set_max_content_height(300)
        preview_scroll.set_margin_start(24)
        preview_scroll.set_margin_end(24)
        preview_scroll.set_margin_bottom(16)

        self._preview_text = Gtk.TextView()
        self._preview_text.set_editable(False)
        self._preview_text.set_wrap_mode(Gtk.WrapMode.WORD)
        self._preview_text.set_monospace(True)
        self._preview_text.set_top_margin(8)
        self._preview_text.set_bottom_margin(8)
        self._preview_text.set_left_margin(8)
        self._preview_text.set_right_margin(8)
        preview_scroll.set_child(self._preview_text)
        content.append(preview_scroll)

    def _refresh_translations(self, _btn=None):
        while row := self._trans_list.get_first_child():
            self._trans_list.remove(row)

        trans_dir = DATA_DIR / "translations"
        if not trans_dir.exists():
            self._status_label.set_text(_("No saved translations found"))
            return

        submitted = _load_submitted()
        import re
        count = 0

        for po_file in sorted(trans_dir.glob("*.po")):
            content = po_file.read_text()
            total = max(0, len(re.findall(r'^msgid ', content, re.MULTILINE)) - 1)
            translated = len(re.findall(r'^msgstr ".+"', content, re.MULTILINE))
            fuzzy_count = len(re.findall(r'^#, fuzzy', content, re.MULTILINE))

            row = Adw.ActionRow()
            pkg_name = po_file.stem

            # Already submitted?
            is_submitted = pkg_name in submitted
            if is_submitted:
                row.set_title(f"✅ {pkg_name}")
                row.set_subtitle(
                    _("%(translated)d/%(total)d strings — Already submitted") % {
                        "translated": translated, "total": total
                    }
                )
            else:
                row.set_title(pkg_name)
                subtitle = _("%(translated)d/%(total)d strings") % {
                    "translated": translated, "total": total
                }
                if fuzzy_count:
                    subtitle += _(" — %d fuzzy") % fuzzy_count
                row.set_subtitle(subtitle)

            icon = "emblem-ok-symbolic" if is_submitted else "document-edit-symbolic"
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))

            check = Gtk.CheckButton()
            check.set_valign(Gtk.Align.CENTER)
            row.add_suffix(check)
            row.po_path = po_file
            row.check = check
            row.is_submitted = is_submitted
            row.fuzzy_count = fuzzy_count
            self._trans_list.append(row)
            count += 1

        self._status_label.set_text(_("%d translations found") % count)

    def _get_selected_files(self) -> list[tuple[Path, bool, int]]:
        """Returns list of (path, already_submitted, fuzzy_count)."""
        files = []
        row = self._trans_list.get_first_child()
        while row:
            if hasattr(row, "check") and row.check.get_active():
                files.append((row.po_path, row.is_submitted, row.fuzzy_count))
            row = row.get_next_sibling()
        return files

    def _build_email(self, pkg_name, po_path):
        config = load_config()
        name = config.get("translator_name", "")
        sender = config.get("email", "")
        lang = config.get("lang_code", "sv")
        lang_name = dict(DEBIAN_LANGUAGES).get(lang, lang)

        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = f"{name} <{sender}>"
        msg["To"] = BTS_EMAIL
        msg["Subject"] = f"{pkg_name}: [INTL:{lang}] {lang_name} translation of debconf templates"

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
        for f, submitted, fuzzy in files:
            msg = self._build_email(f.stem, f)
            text += f"To: {BTS_EMAIL}\nSubject: {msg['Subject']}\nFrom: {msg['From']}\n\n"
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    text += part.get_payload(decode=True).decode()
            if submitted:
                text += "\n⚠ WARNING: This package was already submitted!\n"
            if fuzzy:
                text += f"\n⚠ WARNING: {fuzzy} fuzzy strings!\n"
            text += f"\n[Attachment: {f.stem}.po]\n"
            text += "\n" + "=" * 60 + "\n\n"

        self._preview_text.get_buffer().set_text(text)

    def _on_export(self, _btn):
        files = self._get_selected_files()
        if not files:
            return

        export_dir = DATA_DIR / "bugs"
        export_dir.mkdir(parents=True, exist_ok=True)

        for f, _, _ in files:
            msg = self._build_email(f.stem, f)
            (export_dir / f"{f.stem}-bug.eml").write_text(msg.as_string())

        if self.window:
            self.window.show_success(
                _("Exported"),
                _("Exported %d bug reports to %s") % (len(files), str(export_dir))
            )

    def _on_send(self, _btn):
        files = self._get_selected_files()
        if not files:
            if self.window:
                self.window.show_error(_("Nothing Selected"), _("Select translations to submit."))
            return

        config = load_config()
        if not config.get("email"):
            if self.window:
                self.window.show_error(
                    _("Missing Settings"),
                    _("Please configure your email in Settings (⚙) first.")
                )
            return

        method = config.get("smtp_method", "export")
        if method == "export":
            self._on_export(_btn)
            return

        # Check for warnings
        warnings = []
        resubmits = [f.stem for f, sub, _ in files if sub]
        fuzzy_pkgs = [(f.stem, fz) for f, _, fz in files if fz]

        if resubmits:
            warnings.append(
                _("⚠ Already submitted: %s") % ", ".join(resubmits)
            )
        if fuzzy_pkgs:
            for name, count in fuzzy_pkgs:
                warnings.append(
                    _("⚠ %s has %d fuzzy strings") % (name, count)
                )

        warn_text = "\n".join(warnings)
        confirm_text = _("Send %d bug report(s) to submit@bugs.debian.org?") % len(files)
        if warn_text:
            confirm_text += "\n\n" + warn_text

        dialog = Adw.AlertDialog.new(_("Confirm Submission"), confirm_text)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("send", _("Send"))
        dialog.set_response_appearance("send", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_send_confirmed, files, config)
        dialog.present(self.window)

    def _on_send_confirmed(self, dialog, response, files, config):
        if response != "send":
            return

        method = config.get("smtp_method", "gmail")
        sender = config.get("email", "")
        password = self.window._views.get("settings")
        # Get password from settings view if available
        if password and hasattr(password, "_password_row"):
            pw = password._password_row.get_text()
        else:
            pw = ""

        if not pw:
            if self.window:
                self.window.show_error(
                    _("Missing Password"),
                    _("Enter your password in Settings before sending.")
                )
            return

        if method == "gmail":
            server, port = "smtp.gmail.com", 587
        else:
            server = config.get("smtp_server", "smtp.gmail.com")
            port = config.get("smtp_port", 587)

        self._status_label.set_text(_("Sending…"))

        def do_send():
            results = []
            try:
                smtp = smtplib.SMTP(server, port, timeout=30)
                smtp.ehlo()
                smtp.starttls()
                smtp.login(sender, pw)

                for f, _, _ in files:
                    try:
                        msg = self._build_email(f.stem, f)
                        smtp.sendmail(sender, [BTS_EMAIL], msg.as_string())
                        results.append((f.stem, True, ""))
                    except Exception as e:
                        results.append((f.stem, False, str(e)))

                smtp.quit()
            except Exception as e:
                for f, _, _ in files:
                    results.append((f.stem, False, str(e)))

            GLib.idle_add(self._on_send_done, results)

        threading.Thread(target=do_send, daemon=True).start()

    def _on_send_done(self, results):
        ok = [name for name, success, _ in results if success]
        fail = [(name, err) for name, success, err in results if not success]

        # Mark successful ones as submitted
        if ok:
            submitted = _load_submitted()
            from datetime import datetime
            for name in ok:
                submitted[name] = datetime.now().isoformat()
            _save_submitted(submitted)

        if not fail:
            if self.window:
                self.window.show_success(
                    _("Submitted Successfully"),
                    _("Sent %d translation(s) to Debian BTS:\n%s") % (
                        len(ok), "\n".join(f"✅ {n}" for n in ok)
                    )
                )
            self._refresh_translations()
        else:
            error_text = "\n".join(f"❌ {name}: {err}" for name, err in fail)
            if ok:
                error_text = "\n".join(f"✅ {n}" for n in ok) + "\n" + error_text
            if self.window:
                self.window.show_error(_("Some Submissions Failed"), error_text)

        self._status_label.set_text(
            _("Sent %(ok)d, failed %(fail)d") % {"ok": len(ok), "fail": len(fail)}
        )
