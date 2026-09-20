"""對外契約(interfaces/backend/album/__init__.py)與實作不可走樣。

那份 __init__.py 是其他服務與規格書讀的東西;實作改了卻忘了同步,別人會照著過時的
形狀寫 code。這個測試讓走樣當場變成紅燈。
"""

import importlib.util
import inspect
import re
import sys
from pathlib import Path

import pytest

from app.domains.album.domain import entities as album_entities
from app.domains.album.domain import repositories as album_repositories
from app.domains.drive_export.domain import entities as drive_entities
from app.domains.drive_export.domain import repositories as drive_repositories

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "__init__.py"


@pytest.fixture(scope="module")
def contract():
    spec = importlib.util.spec_from_file_location("album_contract", CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    # @dataclass 在 from __future__ import annotations 下要靠 sys.modules 取模組 globals
    sys.modules["album_contract"] = module
    spec.loader.exec_module(module)
    return module


def _normalize(annotation: str) -> str:
    """抹平「同一個型別的不同寫法」,只比較真正有意義的差異。

    契約檔用 from __future__ import annotations(型別是字串、未加模組前綴),
    實作沒有(型別是真的類別,str() 會帶完整模組路徑)。這裡把兩邊都收斂成
    最後一段名稱:AlbumItem 與 app.domains.album.domain.entities.AlbumItem
    是同一件事,uuid.UUID 與 <class 'uuid.UUID'> 也是。
    """
    annotation = re.sub(r"<(?:class|enum) '([^']+)'>", r"\1", annotation)
    annotation = re.sub(r"Optional\[([^\[\]]+)\]", r"\1 | None", annotation)
    # 去掉模組前綴:foo.bar.Baz -> Baz
    annotation = re.sub(r"\b[\w.]*?(\w+)\b(?!\.)", lambda m: m.group(1), annotation)
    return annotation.replace(" ", "").replace("'", "")


def _public_methods(cls) -> dict[str, str]:
    return {
        name: _normalize(str(inspect.signature(member)))
        for name, member in vars(cls).items()
        if callable(member) and not name.startswith("_")
    }


def _fields(cls) -> dict[str, str]:
    return {f.name: _normalize(str(f.type)) for f in __import__("dataclasses").fields(cls)}


ENTITY_PAIRS = [
    ("AlbumItem", album_entities.AlbumItem),
    ("DriveConnection", drive_entities.DriveConnection),
]
ENUM_PAIRS = [
    ("MediaItemStatus", album_entities.MediaItemStatus),
    ("MediaItemType", album_entities.MediaItemType),
    ("DriveExportStatus", album_entities.DriveExportStatus),
]
REPOSITORY_PAIRS = [
    ("AlbumItemRepository", album_repositories.AlbumItemRepository),
    ("DriveConnectionRepository", drive_repositories.DriveConnectionRepository),
]


@pytest.mark.parametrize(("name", "implementation"), ENTITY_PAIRS, ids=lambda x: str(x))
def test_entity_fields_match(contract, name, implementation):
    assert _fields(getattr(contract, name)) == _fields(implementation)


@pytest.mark.parametrize(("name", "implementation"), ENUM_PAIRS, ids=lambda x: str(x))
def test_enum_values_match(contract, name, implementation):
    assert [m.value for m in getattr(contract, name)] == [m.value for m in implementation]


@pytest.mark.parametrize(("name", "implementation"), REPOSITORY_PAIRS, ids=lambda x: str(x))
def test_repository_signatures_match(contract, name, implementation):
    assert _public_methods(getattr(contract, name)) == _public_methods(implementation)


@pytest.mark.parametrize(("name", "implementation"), REPOSITORY_PAIRS, ids=lambda x: str(x))
def test_repository_interfaces_are_abstract(contract, name, implementation):
    """契約也是 ABC:漏實作方法的人在建立實例當下就會失敗,而不是上線才發現。"""
    contract_cls = getattr(contract, name)

    assert inspect.isabstract(contract_cls)
    assert contract_cls.__abstractmethods__ == implementation.__abstractmethods__


def test_drive_scope_matches(contract):
    assert contract.DRIVE_FILE_SCOPE == drive_entities.DRIVE_FILE_SCOPE


def test_album_item_exposes_the_documented_behaviour(contract):
    """契約上宣告的行為,實體必須真的有。"""
    documented = _public_methods(contract.AlbumItem) | {
        name: "" for name in ("is_ready", "object_keys", "is_exporting")
    }

    for name in documented:
        assert hasattr(album_entities.AlbumItem, name), name
