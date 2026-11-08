"""
Quick launcher for the Rafiq Voice Assistant UI.
Usage:
    python run_ui.py            # Opens native desktop window (with auto-started server)
    python run_ui.py --browser  # Opens in your default web browser
"""
import sys
from ui.app import main

if __name__ == "__main__":
    main()
