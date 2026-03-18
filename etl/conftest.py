"""
Pytest configuration - adds the etl directory to Python path.
"""

import sys
from pathlib import Path

# Add the etl directory to sys.path so absolute imports work
sys.path.insert(0, str(Path(__file__).parent))
