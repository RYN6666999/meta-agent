#!/usr/bin/env python3
# pre-tool-memory-check.py — passthrough (script was missing, recreated)
import sys
import json

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

# Always allow — no blocking logic
sys.exit(0)
