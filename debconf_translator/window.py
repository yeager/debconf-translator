"""Main application window with sidebar navigation."""

import gettext
import logging

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

_ = gettext.gettext
log = logging.getLogger(__name__)

NAV_ITEMS = [
    ("dashboard", "go-home-symbolic", _("Dashboard")),
    ("packages", "package-x-generic-symbolic", _("Packages")),
    ("reviews", "emblem-important-symbolic", _("Review Board")),
    ("submit", "mail-send-symbolic", _("Submit")),
]


class DebconfTranslatorWindow(Adw.ApplicationWindow):
    """Main window with split-view navigation."""

    def __init__(self, **kwargs):
        super().__init__(
            default_width=1200,
            default_height=750,
            title=_("Debconf Translation Manager"),
            **kwargs,
        )
        self._views = {}
        self._current_view = "dashboard"

        self._setup_actions()
        self._build_ui()

    def _setup_actions(self):
        for nav_id, _, _ in NAV_ITEMS:
            action = Gio.SimpleAction.new(f"navigate-{nav_id}", None)
            action.connect("activate", self._on_navigate, nav_id)
            self.add_action(action)

    def _build_ui(self):
        self._split = Adw.NavigationSplitView()
        self._split.set_min_sidebar_width(200)
        self._split.set_max_sidebar_width(260)

        # Sidebar
        sidebar_page = Adw.NavigationPage.new(self._build_sidebar(), _("Navigation"))
        self._split.set_sidebar(sidebar_page)

        # Content
        self._content_stack = Gtk.Stack()
        self._content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Status bar
        self._status_label = Gtk.Label(label=_("Ready"))
        self._status_label.add_css_class("dim-label")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_margin_start(8)
        self._status_label.set_margin_end(8)
        self._status_label.set_margin_top(4)
        self._status_label.set_margin_bottom(4)

        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status_bar.append(self._status_label)

        # Timestamp
        self._time_label = Gtk.Label(label="")
        self._time_label.add_css_class("dim-label")
        self._time_label.set_halign(Gtk.Align.END)
        self._time_label.set_hexpand(True)
        self._time_label.set_margin_end(8)
        status_bar.append(self._time_label)

        content_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_vbox.append(self._content_stack)
        content_vbox.set_vexpand(True)

        content_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_outer.append(content_vbox)
        content_outer.append(Gtk.Separator())
        content_outer.append(status_bar)

        # Content header
        content_header = Adw.HeaderBar()
        self._content_title = Adw.WindowTitle.new(_("Dashboard"), "")
        content_header.set_title_widget(self._content_title)

        theme_btn = Gtk.Button(icon_name="weather-clear-night-symbolic")
        theme_btn.set_tooltip_text(_("Toggle Dark Theme"))
        theme_btn.set_action_name("app.theme")
        content_header.pack_end(theme_btn)

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(content_header)
        content_toolbar.set_content(content_outer)

        content_page = Adw.NavigationPage.new(content_toolbar, _("Content"))
        self._split.set_content(content_page)

        self._add_views()
        self.set_content(self._split)

    def _build_sidebar(self):
        header = Adw.HeaderBar()
        header.set_show_title(True)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(self._build_app_menu())
        header.pack_end(menu_btn)

        sidebar_list = Gtk.ListBox()
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sidebar_list.add_css_class("navigation-sidebar")
        sidebar_list.connect("row-selected", self._on_sidebar_row_selected)

        for nav_id, icon_name, label in NAV_ITEMS:
            row = Adw.ActionRow()
            row.set_title(label)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
            row.nav_id = nav_id
            sidebar_list.append(row)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(sidebar_list)
        scrolled.set_vexpand(True)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(scrolled)

        self._sidebar_list = sidebar_list
        return toolbar

    def _build_app_menu(self):
        menu = Gio.Menu()
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About Debconf Translation Manager"), "app.about")
        return menu

    def _add_views(self):
        from .views.dashboard import DashboardView
        from .views.packages import PackagesView
        from .views.reviews import ReviewsView
        from .views.submit import SubmitView

        view_classes = {
            "dashboard": DashboardView,
            "packages": PackagesView,
            "reviews": ReviewsView,
            "submit": SubmitView,
        }
        for nav_id, cls in view_classes.items():
            view = cls(window=self)
            self._views[nav_id] = view
            self._content_stack.add_named(view, nav_id)

        self._content_stack.set_visible_child_name("dashboard")

    def _on_sidebar_row_selected(self, _listbox, row):
        if row is None:
            return
        self._navigate_to(row.nav_id)

    def _on_navigate(self, _action, _param, nav_id):
        self._navigate_to(nav_id)

    def _navigate_to(self, nav_id):
        self._current_view = nav_id
        self._content_stack.set_visible_child_name(nav_id)
        for nid, _, label in NAV_ITEMS:
            if nid == nav_id:
                self._content_title.set_title(label)
                break

    def open_package_editor(self, pkg):
        """Navigate to packages view and open a specific package."""
        self._navigate_to("packages")
        view = self._views.get("packages")
        if view:
            view.open_package(pkg)
        # Select packages row
        for i, (nid, _, _) in enumerate(NAV_ITEMS):
            if nid == "packages":
                row = self._sidebar_list.get_row_at_index(i)
                if row:
                    self._sidebar_list.select_row(row)
                break

    def set_status(self, text: str):
        self._status_label.set_text(text)
        from datetime import datetime
        self._time_label.set_text(datetime.now().strftime("%H:%M:%S"))
