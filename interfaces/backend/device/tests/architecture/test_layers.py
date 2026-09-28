import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_clean_architecture_dependency_rule():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_layers.py"), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout
