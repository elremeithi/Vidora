"""PyInstaller entry point for the Windows build."""
import sys

from vidora.app import main

if __name__ == "__main__":
    sys.exit(main())
