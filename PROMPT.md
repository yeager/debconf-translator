# Build: Debconf Translation Manager (debconf-translator)

A GTK4/Adwaita app for managing Debian debconf template translations (po-debconf).

## App Identity
- **Name**: Debconf Translation Manager
- **Package**: debconf-translator
- **App ID**: se.danielnylander.DebconfTranslator
- **Module**: debconf_translator
- **Author**: Daniel Nylander <daniel@danielnylander.se>
- **License**: GPL-3.0-or-later
- **Version**: 0.1.0

## Architecture
GTK4/Adwaita split-view with sidebar navigation. Same pattern as freeipa-manager and clipkeeper.

### Navigation (sidebar)
1. **Dashboard** — Overview stats: total strings, translated %, language ranking, progress bar
2. **Packages** — List all packages with po-debconf, filter by: untranslated/partial/complete, popcon score, section. Each row shows: package name, strings count, translation %, popcon rank
3. **Editor** — Built-in PO editor for debconf templates. Side-by-side original/translation. Fuzzy marking, comments, context
4. **Submit** — Generate and preview BTS bug reports with translations. Export .po files. Mail template ready for debian-l10n-swedish@lists.debian.org
5. **History** — Track submitted translations, dates, bug numbers

### Sidebar bottom
- **Settings** button (gear icon) — preferences view with:
  - Simple: default language (dropdown), popcon sorting on/off, auto-save interval
  - Advanced (expander): BTS email, SMTP config, custom debian mirror, cache directory, proxy

### Data Sources
- Scrape https://www.debian.org/international/l10n/po-debconf/{lang} for status
- Download .pot files from https://www.debian.org/international/l10n/po-debconf/pot#{package}
- Popcon data from https://popcon.debian.org/source/by_inst

### Features
- Language selector (all Debian languages, default sv)
- Sort packages by popcon popularity (most-used first)
- Download .pot → create new .po or update existing
- PO editor with: msgid display, msgstr input, fuzzy toggle, translator comments
- Translation Memory: search previously translated strings across packages
- Export .po file
- Generate BTS email body (reportbug format)
- Progress tracking per language
- Offline cache of downloaded templates
- Status bar with connection/cache info
- Theme toggle (dark/light)
- Keyboard shortcuts (Ctrl+S save, Ctrl+F search, Ctrl+N next untranslated)
- CSV/JSON export of statistics
- Welcome dialog on first run

### File Structure
```
debconf_translator/
  __init__.py          (__version__, __app_id__, etc)
  __main__.py
  app.py               (Adw.Application, actions, shortcuts, about, welcome)
  window.py            (main window, sidebar nav, split view)
  cli.py               (argparse CLI: --version, --list, --stats, --export)
  scraper.py           (fetch status, .pot files, popcon from debian.org)
  po_parser.py         (parse/write PO files, translation memory)
  views/
    __init__.py
    dashboard.py
    packages.py
    editor.py
    submit.py
    history.py
    preferences.py
  widgets/
    __init__.py
data/
  se.danielnylander.DebconfTranslator.desktop
  se.danielnylander.DebconfTranslator.svg       (simple icon)
  se.danielnylander.DebconfTranslator.metainfo.xml
po/
  debconf-translator.pot
  README.md
debian/
  control
  rules
  changelog
  compat
  copyright
  install
  debconf-translator.links
pyproject.toml
README.md
LICENSE
.tx/config
```

### Critical Rules
- ALL display names in English
- Swedish ONLY via gettext/Transifex
- Use `Adw.ToolbarView` pattern (NEVER `set_titlebar()`)
- Status bar at bottom of content area
- `Adw.NavigationSplitView` for sidebar
- `Adw.PreferencesGroup` + `Adw.SwitchRow`/`Adw.ComboRow`/`Adw.SpinRow` for settings
- `Adw.AboutDialog` with `present(parent)`
- Include keyboard shortcuts window
- Include "Copy Debug Info" in about
- Desktop file with StartupWMClass
- Metainfo with OARS, releases, screenshots tags
- CLI with --version, --json, -q flags, proper exit codes
- Welcome dialog on first run
- All gettext strings use _() from gettext module
- locale.bindtextdomain + locale.textdomain setup

### PO Parser
Build a simple PO parser (don't require external python-polib dependency):
- Parse .po/.pot files: msgid, msgstr, msgctxt, comments, flags (fuzzy)
- Write .po files with proper formatting
- Translation Memory: store (msgid→msgstr) pairs in SQLite cache

### Scraper
- Use urllib.request (no external deps)
- Cache responses in ~/.cache/debconf-translator/
- Parse HTML with html.parser (stdlib)
- Handle network errors gracefully

### Dependencies (minimal)
- Python 3.10+
- PyGObject (gi)
- GTK4, libadwaita

No external Python packages beyond stdlib + PyGObject.

Build everything. Make it complete and functional.
