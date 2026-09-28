"""streaming 領域的組裝點。共用的基礎設施 provider 在 app/core/dependencies.py。

adapter 本身在 composition root(app/main.py)掛到 app.state,這裡只取出來接成
use case——測試用 dependency_overrides 換成 fake,不需要 Redis、TURN 或 Device 服務。
"""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.dependencies import ClockDep, IdGeneratorDep, SettingsDep
from app.domains.streaming.application.ports import (
    DeviceDirectory,
    SignalingEvents,
    TurnCredentialIssuer,
)
from app.domains.streaming.application.use_cases.answer_offer import AnswerOffer
from app.domains.streaming.application.use_cases.end_stream_session import EndStreamSession
from app.domains.streaming.application.use_cases.exchange_candidates import (
    AddIceCandidates,
    FetchIceCandidates,
)
from app.domains.streaming.application.use_cases.fetch_pending_offer import FetchPendingOffer
from app.domains.streaming.application.use_cases.open_stream_session import OpenStreamSession
from app.domains.streaming.application.use_cases.submit_offer import SubmitOffer
from app.domains.streaming.domain.repositories import StreamSessionRepository


def get_session_repository(request: Request) -> StreamSessionRepository:
    return request.app.state.session_repository


def get_device_directory(request: Request) -> DeviceDirectory:
    return request.app.state.device_directory


def get_turn_issuer(request: Request) -> TurnCredentialIssuer:
    return request.app.state.turn_issuer


def get_signaling_events(request: Request) -> SignalingEvents:
    return request.app.state.signaling_events


SessionRepositoryDep = Annotated[StreamSessionRepository, Depends(get_session_repository)]
DeviceDirectoryDep = Annotated[DeviceDirectory, Depends(get_device_directory)]
TurnIssuerDep = Annotated[TurnCredentialIssuer, Depends(get_turn_issuer)]
SignalingEventsDep = Annotated[SignalingEvents, Depends(get_signaling_events)]


def get_open_stream_session(
    sessions: SessionRepositoryDep,
    devices: DeviceDirectoryDep,
    turn: TurnIssuerDep,
    clock: ClockDep,
    ids: IdGeneratorDep,
    settings: SettingsDep,
) -> OpenStreamSession:
    return OpenStreamSession(
        sessions,
        devices,
        turn,
        clock,
        ids,
        ttl=timedelta(seconds=settings.session_ttl_seconds),
    )


def get_submit_offer(
    sessions: SessionRepositoryDep,
    events: SignalingEventsDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> SubmitOffer:
    return SubmitOffer(
        sessions,
        events,
        clock,
        answer_timeout=timedelta(seconds=settings.answer_wait_timeout_seconds),
    )


def get_answer_offer(
    sessions: SessionRepositoryDep, events: SignalingEventsDep, clock: ClockDep
) -> AnswerOffer:
    return AnswerOffer(sessions, events, clock)


def get_fetch_pending_offer(
    sessions: SessionRepositoryDep, events: SignalingEventsDep, settings: SettingsDep
) -> FetchPendingOffer:
    return FetchPendingOffer(
        sessions,
        events,
        poll_timeout=timedelta(seconds=settings.pending_offer_poll_timeout_seconds),
    )


def get_add_candidates(sessions: SessionRepositoryDep, clock: ClockDep) -> AddIceCandidates:
    return AddIceCandidates(sessions, clock)


def get_fetch_candidates(sessions: SessionRepositoryDep) -> FetchIceCandidates:
    return FetchIceCandidates(sessions)


def get_end_stream_session(sessions: SessionRepositoryDep) -> EndStreamSession:
    return EndStreamSession(sessions)


OpenStreamSessionDep = Annotated[OpenStreamSession, Depends(get_open_stream_session)]
SubmitOfferDep = Annotated[SubmitOffer, Depends(get_submit_offer)]
AnswerOfferDep = Annotated[AnswerOffer, Depends(get_answer_offer)]
FetchPendingOfferDep = Annotated[FetchPendingOffer, Depends(get_fetch_pending_offer)]
AddIceCandidatesDep = Annotated[AddIceCandidates, Depends(get_add_candidates)]
FetchIceCandidatesDep = Annotated[FetchIceCandidates, Depends(get_fetch_candidates)]
EndStreamSessionDep = Annotated[EndStreamSession, Depends(get_end_stream_session)]
