"""測試共用設定。

infrastructure 之外的測試都不碰資料庫:domain 測純函式,application 用 fake,
presentation 用 dependency_overrides 換掉 port,所以這裡不需要任何連線設定。
"""

import os

# 不讓開發機的 .env 影響測試結果
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")
os.environ.setdefault("AUTH_INTERNAL_API_KEY", "test-internal-key")
