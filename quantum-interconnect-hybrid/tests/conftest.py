import sys
from pathlib import Path

# Ensure the package under src/ is importable without installing the project.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))
