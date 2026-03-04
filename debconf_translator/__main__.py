"""Allow running as python3 -m debconf_translator."""
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
