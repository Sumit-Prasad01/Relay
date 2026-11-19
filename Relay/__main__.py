import sys
from pathlib import Path

# Ensure package context when run as a module or script
if __package__ is None or __package__ == "":
    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    __package__ = pkg_dir.name

from .agent import main

if __name__ == "__main__":
    main()
