"""Pytest configuration for notification worker tests."""

import sys
from pathlib import Path

# Add parent directory to path so we can import notification
sys.path.insert(0, str(Path(__file__).parent))
