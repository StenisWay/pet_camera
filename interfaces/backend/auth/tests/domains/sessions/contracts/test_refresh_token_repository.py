"""RefreshTokenRepository 的合約測試(fake 與 SQLAlchemy 各跑一次)。

重點在 revoke() 的回傳值:rotation 的併發勝負完全靠它判定(02_spec 第 2.3.1 節、
規格審查 #11)。fake 與 SQLAlchemy 實作若在這一點上行為不同,application 測試的
綠燈就是假的。
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.sessions.application.ports import SessionsUnitOfWork
from app.domains.sessions.domain.entities import RefreshToken, RevocationReason

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def make_token(user_id: uuid.UUID, fingerprint: str = "fp:secret-1") -> RefreshToken:
    return RefreshToken.issue(
        id=uuid.uuid4(), user_id=user_id, token_hash=fingerprint, now=NOW
    )


async def test_get_by_fingerprint_returns_none_when_absent(
    uow: SessionsUnitOfWork,
) -> None:
    async with uow:
        assert await uow.refresh_tokens.get_by_fingerprint("fp:nothing") is None


async def test_added_token_is_retrievable_after_commit(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.refresh_tokens.add(token)
        await uow.commit()

    async with uow:
        found = await uow.refresh_tokens.get_by_fingerprint(token.token_hash)
        assert found is not None
        assert found.id == token.id
        assert found.expires_at == NOW + timedelta(days=30)


async def test_changes_are_rolled_back_without_commit(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.refresh_tokens.add(token)

    async with uow:
        assert await uow.refresh_tokens.get_by_fingerprint(token.token_hash) is None


async def test_revoke_succeeds_once_and_then_reports_no_op(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID
) -> None:
    """兩個請求同時拿同一個 refresh token 換發時,只有一個能回 True。"""
    token = make_token(owner_id)
    async with uow:
        await uow.refresh_tokens.add(token)
        await uow.commit()

    async with uow:
        assert (
            await uow.refresh_tokens.revoke(
                token.id, revoked_at=NOW, reason=RevocationReason.ROTATED
            )
            is True
        )
        await uow.commit()

    async with uow:
        assert (
            await uow.refresh_tokens.revoke(
                token.id, revoked_at=NOW, reason=RevocationReason.ROTATED
            )
            is False
        )


async def test_revoking_an_unknown_token_reports_no_op(uow: SessionsUnitOfWork) -> None:
    async with uow:
        assert (
            await uow.refresh_tokens.revoke(
                uuid.uuid4(), revoked_at=NOW, reason=RevocationReason.ROTATED
            )
            is False
        )


async def test_revoked_token_is_no_longer_usable(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.refresh_tokens.add(token)
        await uow.commit()
    async with uow:
        await uow.refresh_tokens.revoke(
            token.id, revoked_at=NOW, reason=RevocationReason.ROTATED
        )
        await uow.commit()

    async with uow:
        found = await uow.refresh_tokens.get_by_fingerprint(token.token_hash)
        assert found is not None
        assert found.is_usable(now=NOW) is False


async def test_revoke_all_returns_the_number_actually_revoked(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID
) -> None:
    tokens = [make_token(owner_id, f"fp:secret-{i}") for i in range(3)]
    async with uow:
        for token in tokens:
            await uow.refresh_tokens.add(token)
        await uow.commit()

    async with uow:
        await uow.refresh_tokens.revoke(
            tokens[0].id, revoked_at=NOW, reason=RevocationReason.ROTATED
        )
        await uow.commit()

    async with uow:
        # 已撤銷的那一筆不該再被計入
        revoked = await uow.refresh_tokens.revoke_all_for_user(
            owner_id, revoked_at=NOW, reason=RevocationReason.SUPERSEDED
        )
        assert revoked == 2
        await uow.commit()


async def test_revoke_all_can_keep_the_current_session(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID
) -> None:
    """05_spec 第 2.1 節:改密碼撤銷其他 session,但不把使用者自己踢出去。"""
    keep = make_token(owner_id, "fp:keep")
    other = make_token(owner_id, "fp:other")
    async with uow:
        await uow.refresh_tokens.add(keep)
        await uow.refresh_tokens.add(other)
        await uow.commit()

    async with uow:
        revoked = await uow.refresh_tokens.revoke_all_for_user(
            owner_id,
            revoked_at=NOW,
            reason=RevocationReason.SUPERSEDED,
            except_token_id=keep.id,
        )
        await uow.commit()
    assert revoked == 1

    async with uow:
        survivor = await uow.refresh_tokens.get_by_fingerprint("fp:keep")
        gone = await uow.refresh_tokens.get_by_fingerprint("fp:other")
        assert survivor is not None and survivor.is_usable(now=NOW) is True
        assert gone is not None and gone.is_usable(now=NOW) is False


async def test_revoke_all_only_touches_the_given_user(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID, other_id: uuid.UUID
) -> None:
    mine = make_token(owner_id, "fp:mine")
    theirs = make_token(other_id, "fp:theirs")
    async with uow:
        await uow.refresh_tokens.add(mine)
        await uow.refresh_tokens.add(theirs)
        await uow.commit()

    async with uow:
        revoked = await uow.refresh_tokens.revoke_all_for_user(
            owner_id, revoked_at=NOW, reason=RevocationReason.SUPERSEDED
        )
        assert revoked == 1
        await uow.commit()

    async with uow:
        untouched = await uow.refresh_tokens.get_by_fingerprint("fp:theirs")
        assert untouched is not None and untouched.is_usable(now=NOW) is True


async def test_expired_token_older_than_30_days_is_not_usable(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID
) -> None:
    token = make_token(owner_id)
    async with uow:
        await uow.refresh_tokens.add(token)
        await uow.commit()

    async with uow:
        found = await uow.refresh_tokens.get_by_fingerprint(token.token_hash)
        assert found is not None
        assert found.is_usable(now=NOW + timedelta(days=30, seconds=1)) is False


async def test_delete_all_removes_the_users_tokens(
    uow: SessionsUnitOfWork, owner_id: uuid.UUID, other_id: uuid.UUID
) -> None:
    mine = make_token(owner_id, "fp:mine")
    theirs = make_token(other_id, "fp:theirs")
    async with uow:
        await uow.refresh_tokens.add(mine)
        await uow.refresh_tokens.add(theirs)
        await uow.commit()

    async with uow:
        await uow.refresh_tokens.delete_all_for_user(owner_id)
        await uow.commit()

    async with uow:
        assert await uow.refresh_tokens.get_by_fingerprint("fp:mine") is None
        assert await uow.refresh_tokens.get_by_fingerprint("fp:theirs") is not None
