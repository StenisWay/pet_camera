"""Clean Architecture 的依賴方向不可被破壞。違規時這個測試就紅燈。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dependency_rule_is_not_violated():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_layers.py"), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout
