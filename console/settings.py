"""Shared interface templates; no measured hardware claims."""
import json
from pathlib import Path
CONTROL = json.loads((Path(__file__).resolve().parent /
                     'config/control.json').read_text(encoding='utf-8'))
