"""分層依賴檢查(tools/check_layers.py)跑成測試,違規時紅燈。

放進測試而不是只留一支 CLI,是因為只有進了測試套件才會每次都跑到。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_layer_dependencies_are_not_violated() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "tools" / "check_layers.py"), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
