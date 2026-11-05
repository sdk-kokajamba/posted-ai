"""Tests for PostRepository (run against in-memory SQLite)."""

import sqlite3
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    ChannelCreateData,
    ContentType,
    Post,
    PostCreateData,
    PostStatus,
    PostUpdateData,
    UserCreateData,
)
from bot.db.repositories import ChannelRepository, PostRepository, UserRepository
from bot.exceptions import (
    PostChannelMismatchError,
    PostContentTypeMismatchError,
    PostNotFoundError,
)

# Modern SQLite (>= 3.25.2) preserves the CHECK constraint name in the error
# message; older versions report the expression, so map_integrity_error can't
# resolve the constraint.
_SQLITE_HAS_CHECK_NAMES = sqlite3.sqlite_version_info >= (3, 25, 2)
requires_check_names = pytest.mark.skipif(
    not _SQLITE_HAS_CHECK_NAMES,
    reason="SQLite < 3.25.2 does not preserve CHECK constraint names in errors",
)


async def _create_channel(
    session: AsyncSession,
    *,
    user_id: int = 1,
    tg_id: int = 100,
    name: str = "main",
) -> int:
    await UserRepository(session).get_or_create(
        UserCreateData(user_id=user_id, first_name=f"User{user_id}")
    )
    channel = await ChannelRepository(session).create(
        ChannelCreateData(user_id=user_id, tg_id=tg_id, name=name)
    )
    return channel.id


def _text_post(channel_id: int, *, user_id: int = 1) -> PostCreateData:
    return PostCreateData(
        user_id=user_id,
        channel_id=channel_id,
        theme="t",
        content_type=ContentType.TEXT,
        text="hello",
    )


# ---------------------------------------------------------------------- create


async def test_create_stores_the_post(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)

    post = await repository.create(_text_post(channel_id))

    assert post.id == 1
    assert post.channel_id == channel_id
    assert post.status is PostStatus.MODER
    assert post.content_type is ContentType.TEXT
    assert post.text == "hello"


async def test_create_rejects_text_without_text(session: AsyncSession) -> None:
    """`content_type=text` requires non-empty `text` — pre-check fires first."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)

    with pytest.raises(PostContentTypeMismatchError) as exc_info:
        await repository.create(
            PostCreateData(
                user_id=1,
                channel_id=channel_id,
                theme="t",
                content_type=ContentType.TEXT,
                text=None,
            )
        )

    assert exc_info.value.content_type == "text"
    assert exc_info.value.user_message


async def test_create_rejects_photo_without_media_id(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)

    with pytest.raises(PostContentTypeMismatchError) as exc_info:
        await repository.create(
            PostCreateData(
                user_id=1,
                channel_id=channel_id,
                theme="t",
                content_type=ContentType.PHOTO,
                media_id=None,
            )
        )

    assert exc_info.value.content_type == "photo"


async def test_create_channel_mismatch_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bypass the pre-check: the composite FK (channel_owner) must map to
    PostChannelMismatchError at flush time."""
    await _create_channel(session, user_id=2, tg_id=200, name="other")
    # We know the channel with id=1 belongs to user_id=2.
    repository = PostRepository(session)

    async def _noop(user_id, channel_id):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(repository, "_ensure_channel_belongs_to_user", _noop)

    with pytest.raises(PostChannelMismatchError) as exc_info:
        await repository.create(_text_post(channel_id=1, user_id=1))

    assert exc_info.value.channel_id == 1


@requires_check_names
async def test_create_content_mismatch_race(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bypass the pre-check: the CHECK constraint must map to PostContentTypeMismatchError."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    # ``_ensure_content_matches_type`` is a staticmethod; patch the instance to
    # avoid monkeypatch losing the descriptor on restore.
    monkeypatch.setattr(repository, "_ensure_content_matches_type", lambda *a, **kw: None)

    with pytest.raises(PostContentTypeMismatchError) as exc_info:
        await repository.create(
            PostCreateData(
                user_id=1,
                channel_id=channel_id,
                theme="t",
                content_type=ContentType.TEXT,
                text=None,
            )
        )

    assert exc_info.value.content_type == "text"


# ------------------------------------------------------------------------- get


async def test_get_returns_the_users_post(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    created = await repository.create(_text_post(channel_id))

    fetched = await repository.get(1, created.id)

    assert fetched is created


async def test_get_hides_another_users_post(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    created = await repository.create(_text_post(channel_id))

    with pytest.raises(PostNotFoundError) as exc_info:
        await repository.get(2, created.id)

    assert exc_info.value.post_id == created.id


async def test_get_raises_post_not_found(session: AsyncSession) -> None:
    repository = PostRepository(session)
    with pytest.raises(PostNotFoundError) as exc_info:
        await repository.get(1, 999)
    assert exc_info.value.post_id == 999


# ---------------------------------------------------------------------- update


async def test_update_applies_partial_changes(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    post = await repository.create(_text_post(channel_id))

    updated = await repository.update(1, post.id, PostUpdateData(theme="new", spoiler=True))

    assert updated.theme == "new"
    assert updated.spoiler is True
    assert updated.text == "hello"  # unchanged


async def test_update_validates_resulting_content_state(session: AsyncSession) -> None:
    """Switching to PHOTO without media_id must fail — validation looks at the
    resulting state, not only at the changed fields."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    post = await repository.create(_text_post(channel_id))

    with pytest.raises(PostContentTypeMismatchError) as exc_info:
        await repository.update(1, post.id, PostUpdateData(content_type=ContentType.PHOTO))

    assert exc_info.value.content_type == "photo"


async def test_update_rejects_foreign_channel(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    other_channel = await _create_channel(session, user_id=2, tg_id=200, name="o")
    repository = PostRepository(session)
    post = await repository.create(_text_post(channel_id))

    with pytest.raises(PostChannelMismatchError) as exc_info:
        await repository.update(1, post.id, PostUpdateData(channel_id=other_channel))

    assert exc_info.value.channel_id == other_channel


async def test_update_noop_returns_post_untouched(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    post = await repository.create(_text_post(channel_id))

    result = await repository.update(1, post.id, PostUpdateData())

    assert result is post


# ---------------------------------------------------------------------- delete


async def test_delete_removes_the_post(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    post = await repository.create(_text_post(channel_id))

    await repository.delete(1, post.id)

    with pytest.raises(PostNotFoundError):
        await repository.get(1, post.id)


async def test_delete_rejects_another_users_post(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    post = await repository.create(_text_post(channel_id))

    with pytest.raises(PostNotFoundError) as exc_info:
        await repository.delete(2, post.id)

    assert exc_info.value.post_id == post.id


# --------------------------------------------------------------- list ordering


async def test_list_for_user_sorts_by_pub_date_desc_none_last(
    session: AsyncSession,
) -> None:
    """`coalesce(pub_date, 0).desc()` puts moder posts (pub_date=None) AFTER
    scheduled ones; `id.desc()` provides a stable tiebreaker."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    p100 = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="a",
            content_type=ContentType.TEXT,
            text="x",
            pub_date=100,
        )
    )
    p200 = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="b",
            content_type=ContentType.TEXT,
            text="y",
            pub_date=200,
        )
    )
    pnone = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="c",
            content_type=ContentType.TEXT,
            text="z",
            pub_date=None,
        )
    )

    rows = await repository.list_for_user(1, limit=10)

    assert [p.id for p in rows] == [p200.id, p100.id, pnone.id]


# ---------------------------------------------------------------- bulk: archive


async def test_archive_expired_flips_act_with_past_pub_date(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    post = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="t",
            content_type=ContentType.TEXT,
            text="x",
            status=PostStatus.ACT,
            pub_date=100,
        )
    )

    n = await repository.archive_expired(now=200)
    await session.refresh(post)

    assert n == 1
    assert post.status is PostStatus.ARCH


async def test_archive_expired_skips_future_pub_date(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    post = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="t",
            content_type=ContentType.TEXT,
            text="x",
            status=PostStatus.ACT,
            pub_date=300,
        )
    )

    n = await repository.archive_expired(now=200)
    await session.refresh(post)

    assert n == 0
    assert post.status is PostStatus.ACT


async def test_archive_expired_skips_non_act_and_null_pub_date(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    moder = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="a",
            content_type=ContentType.TEXT,
            text="x",
            status=PostStatus.MODER,
            pub_date=100,
        )
    )
    act_null = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="b",
            content_type=ContentType.TEXT,
            text="y",
            status=PostStatus.ACT,
            pub_date=None,
        )
    )

    n = await repository.archive_expired(now=200)
    await session.refresh(moder)
    await session.refresh(act_null)

    assert n == 0
    assert moder.status is PostStatus.MODER
    assert act_null.status is PostStatus.ACT


async def test_archive_expired_filters_by_user(session: AsyncSession) -> None:
    ch1 = await _create_channel(session, user_id=1, tg_id=100, name="a")
    ch2 = await _create_channel(session, user_id=2, tg_id=200, name="b")
    repository = PostRepository(session)
    p1 = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=ch1,
            theme="t",
            content_type=ContentType.TEXT,
            text="x",
            status=PostStatus.ACT,
            pub_date=100,
        )
    )
    p2 = await repository.create(
        PostCreateData(
            user_id=2,
            channel_id=ch2,
            theme="t",
            content_type=ContentType.TEXT,
            text="y",
            status=PostStatus.ACT,
            pub_date=100,
        )
    )

    n = await repository.archive_expired(now=200, user_id=1)
    await session.refresh(p1)
    await session.refresh(p2)

    assert n == 1
    assert p1.status is PostStatus.ARCH
    assert p2.status is PostStatus.ACT


# -------------------------------------------------- bulk: delete_invalid_moder


async def _insert_broken_moder(
    session: AsyncSession,
    *,
    user_id: int,
    channel_id: int,
    content_type: ContentType,
    created_at: datetime,
) -> int:
    """Seed a "broken" MODER post by temporarily disabling the CHECK constraint.

    `PRAGMA ignore_check_constraints` is the only way to reach that state:
    the CHECK on `posts` normally rejects the INSERT outright. try/finally
    restores the pragma so other tests are not affected.
    """
    await session.execute(text("PRAGMA ignore_check_constraints=ON"))
    try:
        post = Post(
            user_id=user_id,
            channel_id=channel_id,
            theme="t",
            content_type=content_type,
            text=None,
            media_id=None,
            status=PostStatus.MODER,
            created_at=created_at,
        )
        session.add(post)
        await session.flush()
        return post.id
    finally:
        await session.execute(text("PRAGMA ignore_check_constraints=OFF"))


async def test_delete_invalid_moder_deletes_old_broken(session: AsyncSession) -> None:
    """Current semantics: broken MODER older than the cutoff IS deleted."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    broken = await _insert_broken_moder(
        session,
        user_id=1,
        channel_id=channel_id,
        content_type=ContentType.TEXT,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )

    n = await repository.delete_invalid_moder(older_than=datetime(2023, 1, 1, tzinfo=UTC))

    assert n == 1
    assert (await session.scalar(select(Post).where(Post.id == broken))) is None


async def test_delete_invalid_moder_keeps_fresh_broken(session: AsyncSession) -> None:
    """Current semantics: broken MODER younger than the cutoff is NOT deleted."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    broken = await _insert_broken_moder(
        session,
        user_id=1,
        channel_id=channel_id,
        content_type=ContentType.TEXT,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )

    n = await repository.delete_invalid_moder(older_than=datetime(2023, 1, 1, tzinfo=UTC))

    assert n == 0
    assert (await session.scalar(select(Post).where(Post.id == broken))) is not None


async def test_delete_invalid_moder_keeps_old_valid_moder(session: AsyncSession) -> None:
    """Current semantics: even a valid MODER past the cutoff is NOT deleted
    (the method only purges broken content)."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    valid = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="t",
            content_type=ContentType.TEXT,
            text="ok",
            status=PostStatus.MODER,
        )
    )
    # Backdate via direct UPDATE — `onupdate=utcnow` will fire on ORM update,
    # but we write a raw value, and the CHECK on content is satisfied.
    await session.execute(
        text("UPDATE posts SET created_at = :dt WHERE id = :id"),
        {"dt": datetime(2020, 1, 1, tzinfo=UTC).isoformat(), "id": valid.id},
    )

    n = await repository.delete_invalid_moder(older_than=datetime(2023, 1, 1, tzinfo=UTC))

    assert n == 0
    assert (await session.scalar(select(Post).where(Post.id == valid.id))) is not None


async def test_delete_invalid_moder_skips_non_moder(session: AsyncSession) -> None:
    """Non-MODER statuses are untouched by this cleanup even if broken."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    # A valid ACT post — non-MODER, should not be touched.
    act = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="t",
            content_type=ContentType.TEXT,
            text="x",
            status=PostStatus.ACT,
            pub_date=100,
        )
    )

    n = await repository.delete_invalid_moder(older_than=datetime(2025, 1, 1, tzinfo=UTC))

    assert n == 0
    assert (await session.scalar(select(Post).where(Post.id == act.id))) is not None


# ---------------------------------------------- bulk: delete_overdue_published


async def test_delete_overdue_published_deletes_old_pub(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    pub = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="a",
            content_type=ContentType.TEXT,
            text="x",
            status=PostStatus.PUB,
            pub_date=100,
        )
    )
    ap_pub = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="b",
            content_type=ContentType.TEXT,
            text="y",
            status=PostStatus.AP_PUB,
            pub_date=100,
        )
    )

    n = await repository.delete_overdue_published(now=200, retention_seconds=50)

    assert n == 2
    assert (await session.scalar(select(Post).where(Post.id == pub.id))) is None
    assert (await session.scalar(select(Post).where(Post.id == ap_pub.id))) is None


async def test_delete_overdue_published_skips_other_statuses(session: AsyncSession) -> None:
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    ids = []
    for status in (PostStatus.ACT, PostStatus.MODER, PostStatus.ARCH):
        p = await repository.create(
            PostCreateData(
                user_id=1,
                channel_id=channel_id,
                theme=str(status),
                content_type=ContentType.TEXT,
                text="x",
                status=status,
                pub_date=100,
            )
        )
        ids.append(p.id)

    n = await repository.delete_overdue_published(now=1000, retention_seconds=1)

    assert n == 0
    for pid in ids:
        assert (await session.scalar(select(Post).where(Post.id == pid))) is not None


async def test_delete_overdue_published_respects_retention_window(
    session: AsyncSession,
) -> None:
    """Only rows with pub_date < now - retention are deleted."""
    channel_id = await _create_channel(session)
    repository = PostRepository(session)
    old = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="a",
            content_type=ContentType.TEXT,
            text="x",
            status=PostStatus.PUB,
            pub_date=100,
        )
    )
    fresh = await repository.create(
        PostCreateData(
            user_id=1,
            channel_id=channel_id,
            theme="b",
            content_type=ContentType.TEXT,
            text="y",
            status=PostStatus.PUB,
            pub_date=900,
        )
    )

    n = await repository.delete_overdue_published(now=1000, retention_seconds=500)

    assert n == 1
    assert (await session.scalar(select(Post).where(Post.id == old.id))) is None
    assert (await session.scalar(select(Post).where(Post.id == fresh.id))) is not None
