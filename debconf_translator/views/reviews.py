"""Review Board view — shows debconf templates under review on l10n.debian.org."""

import gettext
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib, Gio

from ..scraper import fetch_reviews
from ..models import ReviewItem

_ = gettext.gettext


class ReviewsView(Gtk.Box):
    """Shows active debconf template reviews from l10n.debian.org."""

    def __init__(self, window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.window = window
        self._reviews: list[ReviewItem] = []

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(24)
        header.set_margin_end(24)
        header.set_margin_top(16)

        title = Gtk.Label(label=_("Review Board"))
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text(_("Refresh Reviews"))
        refresh_btn.connect("clicked", lambda _: self.refresh())
        header.append(refresh_btn)

        self.append(header)

        # Description
        desc = Gtk.Label(
            label=_("Templates under review may change. Wait until review is complete before translating.")
        )
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        desc.set_halign(Gtk.Align.START)
        desc.set_margin_start(24)
        desc.set_margin_top(4)
        self.append(desc)

        # Status
        self._status = Gtk.Label(label="")
        self._status.add_css_class("dim-label")
        self._status.set_margin_start(24)
        self._status.set_margin_top(8)
        self._status.set_halign(Gtk.Align.START)
        self.append(self._status)

        # Spinner
        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_margin_top(16)
        self.append(self._spinner)

        # Reviews list
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.connect("row-selected", self._on_review_selected)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self._list_box)
        scrolled.set_vexpand(True)
        scrolled.set_margin_start(24)
        scrolled.set_margin_end(24)
        scrolled.set_margin_top(12)
        scrolled.set_margin_bottom(16)
        self.append(scrolled)

        # Detail pane (side-by-side comparison)
        self._detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._detail_box.set_margin_start(24)
        self._detail_box.set_margin_end(24)
        self._detail_box.set_margin_bottom(16)
        self.append(self._detail_box)

    def refresh(self):
        """Fetch current reviews from l10n.debian.org."""
        self._spinner.start()
        self._status.set_text(_("Fetching reviews…"))

        def do_fetch():
            reviews = fetch_reviews()
            GLib.idle_add(self._on_reviews_loaded, reviews)

        threading.Thread(target=do_fetch, daemon=True).start()

    def _on_reviews_loaded(self, reviews):
        self._spinner.stop()
        self._reviews = reviews

        while row := self._list_box.get_first_child():
            self._list_box.remove(row)

        if not reviews:
            self._status.set_text(_("No active reviews found"))
            return

        self._status.set_text(_("%d packages under review") % len(reviews))

        for review in reviews:
            row = Adw.ActionRow()
            row.set_title(review.package)

            # Status badge
            status_text = review.status or _("review")
            subtitle = status_text
            if review.bug_number:
                subtitle += f" — Bug #{review.bug_number}"
            row.set_subtitle(subtitle)

            # Icon based on status
            icon = "dialog-warning-symbolic" if review.status == "bts" else "emblem-important-symbolic"
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))

            # Open in browser button
            if review.bug_number:
                web_btn = Gtk.Button(icon_name="web-browser-symbolic")
                web_btn.set_tooltip_text(_("Open Bug in Browser"))
                web_btn.set_valign(Gtk.Align.CENTER)
                web_btn.add_css_class("flat")
                web_btn.connect("clicked", self._on_open_bug, review.bug_number)
                row.add_suffix(web_btn)

            row.review = review
            self._list_box.append(row)

    def _on_review_selected(self, _listbox, row):
        """Show review details with side-by-side comparison."""
        while child := self._detail_box.get_first_child():
            self._detail_box.remove(child)

        if row is None or not hasattr(row, "review"):
            return

        review = row.review

        # Detail card
        detail_group = Adw.PreferencesGroup()
        detail_group.set_title(_("Review Details: %s") % review.package)

        if review.status:
            status_row = Adw.ActionRow()
            status_row.set_title(_("Status"))
            status_row.set_subtitle(review.status)
            detail_group.add(status_row)

        if review.bug_number:
            bug_row = Adw.ActionRow()
            bug_row.set_title(_("Bug Number"))
            bug_row.set_subtitle(f"#{review.bug_number}")
            detail_group.add(bug_row)

        # Side-by-side comparison (if we have old/new strings)
        if review.original_strings and review.new_strings:
            compare_label = Gtk.Label(label=_("String Changes:"))
            compare_label.add_css_class("heading")
            compare_label.set_halign(Gtk.Align.START)
            compare_label.set_margin_top(8)
            self._detail_box.append(compare_label)

            for old, new in zip(review.original_strings, review.new_strings):
                compare_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                compare_box.set_margin_top(4)

                old_frame = Gtk.Frame()
                old_label = Gtk.Label(label=old)
                old_label.set_wrap(True)
                old_label.set_margin_start(8)
                old_label.set_margin_end(8)
                old_label.set_margin_top(4)
                old_label.set_margin_bottom(4)
                old_label.add_css_class("error")
                old_frame.set_child(old_label)
                old_frame.set_hexpand(True)
                compare_box.append(old_frame)

                arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
                compare_box.append(arrow)

                new_frame = Gtk.Frame()
                new_label = Gtk.Label(label=new)
                new_label.set_wrap(True)
                new_label.set_margin_start(8)
                new_label.set_margin_end(8)
                new_label.set_margin_top(4)
                new_label.set_margin_bottom(4)
                new_label.add_css_class("success")
                new_frame.set_child(new_label)
                new_frame.set_hexpand(True)
                compare_box.append(new_frame)

                self._detail_box.append(compare_box)

        info_label = Gtk.Label(
            label=_("⚠ Do not translate this package until the review is complete.")
        )
        info_label.add_css_class("warning")
        info_label.set_wrap(True)
        info_label.set_halign(Gtk.Align.START)
        info_label.set_margin_top(12)
        self._detail_box.append(info_label)

        self._detail_box.append(detail_group)

    def _on_open_bug(self, _btn, bug_number):
        """Open bug report in browser."""
        import subprocess
        url = f"https://bugs.debian.org/{bug_number}"
        try:
            subprocess.Popen(["xdg-open", url])
        except FileNotFoundError:
            pass
