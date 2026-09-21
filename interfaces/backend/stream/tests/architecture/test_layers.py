"""分層依賴規則是測試的一部分,不靠自律。

違規時直接紅燈,並印出 tools/check_layers.py 的完整報告。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_clean_architecture_dependency_rule() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_layers.py"), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
