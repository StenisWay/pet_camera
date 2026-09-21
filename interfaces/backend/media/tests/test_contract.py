"""對外契約(media/__init__.py)與實作不可走樣。

__init__.py 是給其他服務與規格書讀的東西。它悄悄過期比沒有更糟——別人會照著一份
不存在的介面寫程式。這個測試讓走樣當場變紅燈。
"""

import importlib
import inspect
import sys
from pathlib import Path

import pytest

from app.domains.media.domain.entities import MediaItemStatus, MediaItemType
from app.domains.media.domain.repositories import MediaItemRepository

SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def contract():
    """把 interfaces/backend/ 放進路徑,以 `media` 套件的身分載入對外契約。"""
    backend_root = SERVICE_ROOT.parent
    sys.path.insert(0, str(backend_root))
    try:
        yield importlib.import_module("media")
    finally:
        sys.path.remove(str(backend_root))


def test_status_values_match_the_contract(contract):
    assert {s.value for s in MediaItemStatus} == {s.value for s in contract.MediaItemStatus}


def test_type_values_match_the_contract(contract):
    assert {t.value for t in MediaItemType} == {t.value for t in contract.MediaItemType}


def test_repository_exposes_every_method_the_contract_promises(contract):
    promised = {
        name
        for name, _ in inspect.getmembers(contract.MediaItemRepository, inspect.isfunction)
        if not name.startswith("_")
    }

    missing = promised - set(dir(MediaItemRepository))

    assert not missing, f"對外契約宣告了但實作沒有的方法:{sorted(missing)}"


def test_repository_signatures_match_the_contract(contract):
    """參數名稱也算契約的一部分——別的服務會用關鍵字引數呼叫。"""
    for name in ("get", "add", "save", "find_active_clip", "list_stale_processing"):
        promised = inspect.signature(getattr(contract.MediaItemRepository, name))
        actual = inspect.signature(getattr(MediaItemRepository, name))

        assert list(promised.parameters) == list(actual.parameters), name


def test_contract_item_allows_processing_state(contract):
    """資料模型 §2.4:processing 期間 object_key 為 null(規格審查 #16 修正的地方)。"""
    field = contract.MediaItem.model_fields["object_key"]

    assert not field.is_required()
