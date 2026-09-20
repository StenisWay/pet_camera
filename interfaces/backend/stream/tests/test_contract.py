"""對外契約(interfaces/backend/stream/__init__.py)與實作不可走樣。

那份 __init__.py 是其他服務與規格書讀的東西;實作改了卻忘了同步,別人會照著過時的
形狀寫 code。這個測試讓走樣當場變成紅燈。
"""

import dataclasses
import importlib.util
import inspect
import re
import sys
from pathlib import Path

import pytest

from app.domains.streaming.domain import entities, repositories, value_objects

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "__init__.py"


@pytest.fixture(scope="module")
def contract():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("stream_contract", CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    # @dataclass 在 from __future__ import annotations 下要靠 sys.modules 取模組 globals
    sys.modules["stream_contract"] = module
    spec.loader.exec_module(module)
    return module


def _normalize(annotation: str) -> str:
    """抹平「同一個型別的不同寫法」,只比較真正有意義的差異。

    契約檔用 from __future__ import annotations(型別是字串、未加模組前綴),
    實作的 value_objects 也是,但 entities 取到的會帶模組路徑。這裡把兩邊都收斂成
    最後一段名稱:IceCandidate 與 app...value_objects.IceCandidate 是同一件事。
    """
    annotation = re.sub(r"<(?:class|enum) '([^']+)'>", r"\1", annotation)
    annotation = re.sub(r"Optional\[([^\[\]]+)\]", r"\1 | None", annotation)
    annotation = re.sub(r"\b[\w.]*?(\w+)\b(?!\.)", lambda m: m.group(1), annotation)
    return annotation.replace(" ", "").replace("'", "")


def _fields(cls) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {f.name: _normalize(str(f.type)) for f in dataclasses.fields(cls)}


def _public_methods(cls) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {
        name: _normalize(str(inspect.signature(member)))
        for name, member in vars(cls).items()
        if callable(member) and not name.startswith("_")
    }


DATACLASS_PAIRS = [
    ("TurnCredentials", value_objects.TurnCredentials),
    ("IceCandidate", value_objects.IceCandidate),
    ("DeviceSnapshot", value_objects.DeviceSnapshot),
    ("StreamSession", entities.StreamSession),
]
ENUM_PAIRS = [
    ("DeviceStatus", value_objects.DeviceStatus),
    ("SignalingState", entities.SignalingState),
    ("Peer", entities.Peer),
]


@pytest.mark.parametrize(("name", "implementation"), DATACLASS_PAIRS, ids=lambda x: str(x))
def test_dataclass_fields_match(contract, name, implementation) -> None:  # type: ignore[no-untyped-def]
    assert _fields(getattr(contract, name)) == _fields(implementation)


@pytest.mark.parametrize(("name", "implementation"), ENUM_PAIRS, ids=lambda x: str(x))
def test_enum_values_match(contract, name, implementation) -> None:  # type: ignore[no-untyped-def]
    assert [m.value for m in getattr(contract, name)] == [m.value for m in implementation]


def test_repository_signatures_match(contract) -> None:  # type: ignore[no-untyped-def]
    assert _public_methods(contract.StreamSessionRepository) == _public_methods(
        repositories.StreamSessionRepository
    )


def test_repository_is_abstract(contract) -> None:  # type: ignore[no-untyped-def]
    """契約也是 ABC:漏實作方法的人在建立實例當下就會失敗,而不是上線才發現。"""
    assert inspect.isabstract(contract.StreamSessionRepository)
    assert (
        contract.StreamSessionRepository.__abstractmethods__
        == repositories.StreamSessionRepository.__abstractmethods__
    )


def test_heartbeat_timeout_matches(contract) -> None:  # type: ignore[no-untyped-def]
    """90 秒是業務門檻,契約與實作講的必須是同一個數字。"""
    assert contract.HEARTBEAT_TIMEOUT == value_objects.HEARTBEAT_TIMEOUT


def test_documented_session_behaviour_exists(contract) -> None:  # type: ignore[no-untyped-def]
    """契約 docstring 上宣告的行為,實體必須真的有。"""
    documented = (
        "open",
        "is_expired",
        "is_owned_by",
        "submit_offer",
        "accept_answer",
        "add_candidate",
        "candidates_for",
    )

    for name in documented:
        assert hasattr(entities.StreamSession, name), name


def test_documented_snapshot_behaviour_exists(contract) -> None:  # type: ignore[no-untyped-def]
    for name in _public_methods(contract.DeviceSnapshot):
        assert hasattr(value_objects.DeviceSnapshot, name), name
