"""把分層規則變成測試套件的一部分。

Refactor 階段若不小心讓 domain import 了 SQLAlchemy、或讓 application 依賴 FastAPI,
這個測試會立刻紅燈,而不是等到程式碼審查才被發現。
"""

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

    assert result.returncode == 0, result.stdout + result.stderr
