# Debconf Translation Manager

A GTK4/Adwaita tool for managing Debconf template translations in Debian and Ubuntu.

<img width="1206" height="754" alt="image" src="https://github.com/user-attachments/assets/801eb597-ecab-428d-a843-f3fc85bb7e00" />


## Features

- **Dashboard** — Overview of translation status per language with statistics
- **Package Browser** — Browse untranslated packages sorted by popularity (popcon)
- **Built-in PO Editor** — Edit translations inline with source/translation side-by-side
- **Review Board** — Track debconf templates under review on l10n.debian.org
- **BTS Submission** — Generate bug reports for submitting translations
- **CLI** — Command-line interface for status checks and batch operations

## Installation

### From .deb package (Debian/Ubuntu)
```bash
# Add the repository
echo "deb https://yeager.github.io/debian-repo/ stable main" | sudo tee /etc/apt/sources.list.d/yeager.list
sudo apt update && sudo apt install debconf-translator
```

### From .rpm package (Fedora)
```bash
sudo dnf install debconf-translator
```

### From source
```bash
pip install .
debconf-translator
```

## Usage

### GUI
```bash
debconf-translator
```

### CLI
```bash
# Check translation status
debconf-translator status sv
debconf-translator status sv --json

# Download untranslated templates
debconf-translator fetch sv -o ./translations/

# Show packages under review
debconf-translator reviews
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+1 | Dashboard |
| Ctrl+2 | Packages |
| Ctrl+3 | Review Board |
| Ctrl+4 | Submit |
| Ctrl+T | Toggle Dark Theme |
| Ctrl+Q | Quit |

## Translation

Translations are managed on [Transifex](https://www.transifex.com/danielnylander/debconf-translator/).

## License

GPL-3.0-or-later

## Author

Daniel Nylander <daniel@danielnylander.se>
