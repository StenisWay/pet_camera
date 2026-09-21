"""對外契約(interfaces/backend/push/__init__.py)與實作不可走樣。

那份 __init__.py 是其他服務(Event 的 worker、前端)與規格書讀的東西;實作改了卻忘了
同步,別人會照著過時的形狀寫 code。這個測試讓走樣當場變成紅燈。
"""

import dataclasses
import importlib.util
import inspect
import re
import sys
from pathlib import Path

import pytest

from app.domains.notifications.presentation.schemas import EventReadyIn
from app.domains.push_tokens.domain import entities, repositories
from app.main import create_app

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "__init__.py"


@pytest.fixture(scope="module")
def contract():
    spec = importlib.util.spec_from_file_location("push_contract", CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    # @dataclass 在 from __future__ import annotations 下要靠 sys.modules 取模組 globals
    sys.modules["push_contract"] = module
    spec.loader.exec_module(module)
    return module


def _normalize(annotation: str) -> str:
    """抹平「同一個型別的不同寫法」:契約檔的字串註記 vs 實作的真實類別。"""
    annotation = re.sub(r"<(?:class|enum) '([^']+)'>", r"\1", annotation)
    annotation = re.sub(r"Optional\[([^\[\]]+)\]", r"\1 | None", annotation)
    annotation = re.sub(r"\b[\w.]*?(\w+)\b(?!\.)", lambda m: m.group(1), annotation)
    return annotation.replace(" ", "").replace("'", "")


def _fields(cls) -> dict[str, str]:
    return {f.name: _normalize(str(f.type)) for f in dataclasses.fields(cls)}


def _public_methods(cls) -> dict[str, str]:
    return {
        name: _normalize(str(inspect.signature(member)))
        for name, member in vars(cls).items()
        if callable(member) and not name.startswith("_")
    }


def test_push_token_fields_match(contract):
    assert _fields(contract.PushToken) == _fields(entities.PushToken)


def test_client_platform_values_match(contract):
    assert [m.value for m in contract.ClientPlatform] == [m.value for m in entities.ClientPlatform]


def test_repository_signatures_match(contract):
    assert _public_methods(contract.PushTokenRepository) == _public_methods(
        repositories.PushTokenRepository
    )


def test_repository_contract_is_abstract(contract):
    assert (
        contract.PushTokenRepository.__abstractmethods__
        == repositories.PushTokenRepository.__abstractmethods__
    )


def test_event_ready_body_matches_the_endpoint(contract):
    """Event worker 照契約組 body;欄位與實際端點的 schema 必須一致(09_spec 第 3 節)。"""
    assert [f.name for f in dataclasses.fields(contract.EventReadyNotification)] == list(
        EventReadyIn.model_fields
    )


def test_documented_endpoints_are_exactly_the_routes(contract):
    # 讀 OpenAPI 而非 app.routes:新版 FastAPI 的 include_router 不再攤平成 APIRoute
    paths = create_app(lifespan_enabled=False).openapi()["paths"]
    routes = {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if path.startswith(("/push-tokens", "/internal"))
    }

    assert routes == set(contract.ENDPOINTS)
