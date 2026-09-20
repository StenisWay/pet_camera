"""對外契約(event/__init__.py)與實作必須一致。

那份檔案是給其他服務與規格書讀的。沒有這個測試,它會在幾次重構之後悄悄過期,
然後別的服務照著過期的形狀寫出接不起來的程式碼。
"""

import importlib.util
import inspect
import sys
from dataclasses import fields
from pathlib import Path

import pytest

from app.domains.detection.application import ports as detection_ports
from app.domains.detection.domain import entities as detection_entities
from app.domains.detection.domain import recording
from app.domains.detection.domain import repositories as detection_repos
from app.domains.timeline.application import ports as timeline_ports
from app.domains.timeline.domain import entities as timeline_entities
from app.domains.timeline.domain import value_objects


def _load_contract():
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("event_contract", path)
    module = importlib.util.module_from_spec(spec)
    # dataclass 會回頭查 sys.modules[cls.__module__],不先登記會在裝飾時就爆
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contract = _load_contract()


# --- 常數 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "actual"),
    [
        ("MOTION_THRESHOLD", recording.MOTION_THRESHOLD),
        ("SILENCE_TIMEOUT", recording.SILENCE_TIMEOUT),
        ("MAX_RECORDING_DURATION", recording.MAX_RECORDING_DURATION),
        ("VIDEO_RETENTION", timeline_entities.VIDEO_RETENTION),
        ("THUMBNAIL_RETENTION", timeline_entities.THUMBNAIL_RETENTION),
        ("DEFAULT_PAGE_SIZE", value_objects.DEFAULT_PAGE_SIZE),
        ("MAX_PAGE_SIZE", value_objects.MAX_PAGE_SIZE),
        ("DEFAULT_TIMEZONE", value_objects.DEFAULT_TIMEZONE),
    ],
)
def test_constants_match_the_contract(name, actual):
    assert getattr(contract, name) == actual


def test_upload_attempts_match_the_contract():
    from app.domains.detection.application.use_cases.finish_recording import (
        UPLOAD_MAX_ATTEMPTS,
    )

    assert contract.UPLOAD_MAX_ATTEMPTS == UPLOAD_MAX_ATTEMPTS


# --- 列舉 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "actual"),
    [
        ("EventType", detection_entities.EventType),
        ("EventStatus", detection_entities.EventStatus),
        ("StopReason", recording.StopReason),
    ],
)
def test_enum_values_match_the_contract(name, actual):
    expected = {m.name: m.value for m in getattr(contract, name)}
    assert {m.name: m.value for m in actual} == expected


def test_timeline_uses_the_same_status_values():
    """兩個領域各自定義 EventStatus,但值域必須相同——它們對應同一個 CHECK 約束。"""
    assert {m.value for m in timeline_entities.EventStatus} == {
        m.value for m in detection_entities.EventStatus
    }


# --- 型別的欄位 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "actual"),
    [
        ("Event", detection_entities.Event),
        ("UploadedMedia", detection_entities.UploadedMedia),
        ("RecordingSession", recording.RecordingSession),
        ("TimelineEvent", timeline_entities.TimelineEvent),
        ("PurgedEvents", detection_repos.PurgedEvents),
        ("TimelineCursor", value_objects.TimelineCursor),
    ],
)
def test_dataclass_fields_match_the_contract(name, actual):
    expected = {f.name for f in fields(getattr(contract, name))}
    assert {f.name for f in fields(actual)} == expected


# --- 介面 ---------------------------------------------------------------


def _params(func) -> list[tuple[str, inspect._ParameterKind]]:
    return [(p.name, p.kind) for p in inspect.signature(func).parameters.values()]


@pytest.mark.parametrize(
    ("name", "actual"),
    [
        ("EventRepository", detection_repos.EventRepository),
        ("PushNotifier", detection_ports.PushNotifier),
        ("DeviceOwnership", timeline_ports.DeviceOwnership),
    ],
)
def test_interface_methods_match_the_contract(name, actual):
    expected = getattr(contract, name)
    assert actual.__abstractmethods__ == expected.__abstractmethods__

    for method in sorted(actual.__abstractmethods__):
        # 只比參數的名稱與種類(位置/關鍵字),不比型別註解:契約用了
        # `from __future__ import annotations`,註解是字串、還少了模組前綴,
        # 比下去只會比到書寫差異。真正會讓呼叫端壞掉的是參數本身。
        assert _params(getattr(actual, method)) == _params(
            getattr(expected, method)
        ), f"{name}.{method} 的參數與契約不符"


def test_object_storage_is_split_into_two_narrow_ports():
    """契約把 R2 寫成一個 ObjectStorage,實作刻意拆成兩個窄介面。

    detection 只需要 upload / delete_many,timeline 只需要 presigned_url;
    以各自領域的語言命名,誰也不會拿到用不到的能力。合起來要覆蓋契約的三個方法。
    """
    contract_methods = set(contract.ObjectStorage.__abstractmethods__)
    actual = set(detection_ports.MediaUploader.__abstractmethods__) | set(
        timeline_ports.MediaUrlIssuer.__abstractmethods__
    )

    assert contract_methods == actual
