#!/usr/bin/env python3
"""Repository entrypoint; all reusable code travels with the skill folder."""
from pathlib import Path
import runpy
import sys

scripts = Path(__file__).resolve().parent / 'skills/mai-habit/scripts'
sys.path.insert(0, str(scripts))
runpy.run_path(str(scripts / 'main.py'), run_name='__main__')
