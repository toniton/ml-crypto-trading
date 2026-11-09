"""Package entrypoint when invoked with python -m installer."""

import sys
from installer.cli import main

if __name__ == "__main__":
    sys.exit(main())
