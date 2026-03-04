"""Debconf Translation Manager — GTK4/Adwaita tool for managing Debconf template translations."""

import gettext
import locale
import os

__version__ = "0.4.0"
__app_id__ = "se.danielnylander.debconf-translator"
__author__ = "Daniel Nylander"
__email__ = "daniel@danielnylander.se"

# Centralized locale/gettext setup — all modules import _ from here
_localedir = os.path.join(os.path.dirname(__file__), '..', 'locale')
if not os.path.isdir(_localedir):
    _localedir = '/usr/share/locale'

try:
    locale.bindtextdomain('debconf-translator', _localedir)
    locale.textdomain('debconf-translator')
except AttributeError:
    pass  # macOS

gettext.bindtextdomain('debconf-translator', _localedir)
gettext.textdomain('debconf-translator')

_ = gettext.gettext
