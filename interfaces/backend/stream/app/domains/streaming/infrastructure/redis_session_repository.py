"""StreamSessionRepository 的 Redis 實作。

key 形狀見 01_資料模型與儲存規格.md 第 7 節與 06_spec 第 2.4 節:

    stream:session:{session_id} -> 序列化的 session,TTL = 剩餘效期
    stream:device:{device_id}   -> session_id,同 TTL(供接管與「誰在看」查詢)

接管靠覆寫裝置索引 + 刪除舊 session(last-writer-wins),不需要分散式鎖。
Redis 不可用時一律拋 ServiceUnavailable(SRV_002);DELETE 的 fail-open 由
use case 決定,不在這一層吞掉例外。
"""

import json
import math
import uuid
from datetime import datetime
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.domains.streaming.domain.entities import Peer, SignalingState, StreamSession
from app.domains.streaming.domain.repositories import StreamSessionRepository
from app.domains.streaming.domain.value_objects import IceCandidate, TurnCredentials
from app.shared_kernel.errors import ServiceUnavailable
from app.shared_kernel.ports import Clock

SESSION_KEY = "stream:session:{session_id}"
DEVICE_KEY = "stream:device:{device_id}"


class RedisStreamSessionRepository(StreamSessionRepository):
    def __init__(self, client: redis.Redis, clock: Clock) -> None:
        self._client = client
        self._clock = clock

    async def get(self, session_id: uuid.UUID) -> StreamSession | None:
        raw = await self._guard(self._client.get(SESSION_KEY.format(session_id=session_id)))
        if raw is None:
            return None
        session = _deserialize(raw)
        # key TTL 與 expires_at 理論上同步,這裡再擋一次:Redis 的到期是惰性的,
        # 而「到期即失效」是業務規則,不該依賴清除時機
        if session.is_expired(self._clock.now()):
            return None
        return session

    async def get_active_for_device(self, device_id: uuid.UUID) -> StreamSession | None:
        raw = await self._guard(self._client.get(DEVICE_KEY.format(device_id=device_id)))
        if raw is None:
            return None
        return await self.get(uuid.UUID(raw))

    async def save(self, session: StreamSession) -> None:
        ttl = self._ttl_seconds(session.expires_at)
        if ttl <= 0:
            # 已經過期的東西不必寫進去
            return

        device_key = DEVICE_KEY.format(device_id=session.device_id)
        previous = await self._guard(self._client.get(device_key))

        pipeline = self._client.pipeline()
        if previous is not None and previous != str(session.id):
            # 接管:舊 session_id 之後必須讀不到(第 2.4 節)
            pipeline.delete(SESSION_KEY.format(session_id=uuid.UUID(previous)))
        pipeline.set(SESSION_KEY.format(session_id=session.id), _serialize(session), ex=ttl)
        pipeline.set(device_key, str(session.id), ex=ttl)
        await self._guard(pipeline.execute())

    async def delete(self, session_id: uuid.UUID) -> None:
        session_key = SESSION_KEY.format(session_id=session_id)
        raw = await self._guard(self._client.get(session_key))

        pipeline = self._client.pipeline()
        pipeline.delete(session_key)
        if raw is not None:
            device_key = DEVICE_KEY.format(device_id=_deserialize(raw).device_id)
            # 只有索引還指向這個 session 才刪——否則會把接管後那個新 session 的索引
            # 一起刪掉,新的觀看端就再也找不到自己的連線
            current = await self._guard(self._client.get(device_key))
            if current == str(session_id):
                pipeline.delete(device_key)
        await self._guard(pipeline.execute())

    def _ttl_seconds(self, expires_at: datetime) -> int:
        return math.ceil((expires_at - self._clock.now()).total_seconds())

    @staticmethod
    async def _guard(awaitable: Any) -> Any:
        try:
            return await awaitable
        except RedisError as exc:
            raise ServiceUnavailable() from exc


def _serialize(session: StreamSession) -> str:
    return json.dumps(
        {
            "id": str(session.id),
            "device_id": str(session.device_id),
            "owner_id": str(session.owner_id),
            "turn_credentials": {
                "urls": list(session.turn_credentials.urls),
                "username": session.turn_credentials.username,
                "credential": session.turn_credentials.credential,
                "expires_at": session.turn_credentials.expires_at.isoformat(),
            },
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "state": session.state.value,
            "offer_sdp": session.offer_sdp,
            "answer_sdp": session.answer_sdp,
            "viewer_candidates": [_candidate_json(c) for c in session.viewer_candidates],
            "camera_candidates": [_candidate_json(c) for c in session.camera_candidates],
        },
        separators=(",", ":"),
    )


def _candidate_json(candidate: IceCandidate) -> dict[str, Any]:
    return {
        "sdp_mid": candidate.sdp_mid,
        "sdp_m_line_index": candidate.sdp_m_line_index,
        "candidate": candidate.candidate,
    }


def _deserialize(raw: str) -> StreamSession:
    data = json.loads(raw)
    credentials = data["turn_credentials"]
    return StreamSession(
        id=uuid.UUID(data["id"]),
        device_id=uuid.UUID(data["device_id"]),
        owner_id=uuid.UUID(data["owner_id"]),
        turn_credentials=TurnCredentials(
            urls=tuple(credentials["urls"]),
            username=credentials["username"],
            credential=credentials["credential"],
            expires_at=datetime.fromisoformat(credentials["expires_at"]),
        ),
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        state=SignalingState(data["state"]),
        offer_sdp=data["offer_sdp"],
        answer_sdp=data["answer_sdp"],
        viewer_candidates=[_to_candidate(c) for c in data["viewer_candidates"]],
        camera_candidates=[_to_candidate(c) for c in data["camera_candidates"]],
    )


def _to_candidate(data: dict[str, Any]) -> IceCandidate:
    return IceCandidate(
        sdp_mid=data["sdp_mid"],
        sdp_m_line_index=data["sdp_m_line_index"],
        candidate=data["candidate"],
    )


__all__ = ["DEVICE_KEY", "SESSION_KEY", "Peer", "RedisStreamSessionRepository"]
