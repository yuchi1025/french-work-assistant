import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"

src_path_text = str(SRC_PATH)
if src_path_text not in sys.path:
    sys.path.insert(0, src_path_text)
