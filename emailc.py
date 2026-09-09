#!/usr/bin/env python3
"""Launcher so `./emailc.py` works from a clone without installing."""
import sys
from emailc.cli import main
sys.exit(main())
