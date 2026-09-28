"""push_tokens 的組裝點。共用的基礎設施 provider 在 app/core/dependencies.py。"""

from typing import Annotated

from fastapi import Depends

from app.core.dependencies import ClockDep, IdGeneratorDep, SessionFactoryDep
from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from app.domains.push_tokens.application.use_cases.list_push_tokens import ListPushTokens
from app.domains.push_tokens.application.use_cases.register_push_token import RegisterPushToken
from app.domains.push_tokens.application.use_cases.unregister_push_token import (
    UnregisterPushToken,
)
from app.domains.push_tokens.infrastructure.unit_of_work import SqlAlchemyPushTokensUnitOfWork


def get_push_tokens_uow(session_factory: SessionFactoryDep) -> PushTokensUnitOfWork:
    return SqlAlchemyPushTokensUnitOfWork(session_factory)


PushTokensUowDep = Annotated[PushTokensUnitOfWork, Depends(get_push_tokens_uow)]


def get_register_push_token(
    uow: PushTokensUowDep, ids: IdGeneratorDep, clock: ClockDep
) -> RegisterPushToken:
    return RegisterPushToken(uow, ids, clock)


def get_list_push_tokens(uow: PushTokensUowDep) -> ListPushTokens:
    return ListPushTokens(uow)


def get_unregister_push_token(uow: PushTokensUowDep) -> UnregisterPushToken:
    return UnregisterPushToken(uow)


RegisterPushTokenDep = Annotated[RegisterPushToken, Depends(get_register_push_token)]
ListPushTokensDep = Annotated[ListPushTokens, Depends(get_list_push_tokens)]
UnregisterPushTokenDep = Annotated[UnregisterPushToken, Depends(get_unregister_push_token)]
