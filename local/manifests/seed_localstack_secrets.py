#!/usr/bin/env python3
"""Compatibility entrypoint; all secret payloads use private state and stdin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from localdev.secret_store import main

if __name__ == "__main__":
    main()
