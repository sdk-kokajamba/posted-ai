"""Tests for PostRepository (run against in-memory SQLite)."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Channel,
    ChannelCreateData,
    ContentType,
    Post,
    PostCreateData,
    PostStatus,
    PostUpdateData,
    User,
)
from bot.db.models.user import UserCreateData
from bot.db.repositories import (
    ChannelRepository,
    PostRepository,
    UserRepository,
)
from bot.exceptions import (
    PostChannelMismatchError,
    PostContentTypeMismatchError,
    PostNotFoundError,
)

# ---------------------------------------------------------------- fixtures


@pytest.fixture
async def user(session: AsyncSession) -> User:
    """Создаёт пользователя и возвращает его."""
    repo = UserRepository(session)
    user, _ = await repo.get_or_create(
        UserCreateData(
            user_id=1,
            username="testuser",
            first_name="Test",
            language_code="ru",
        )
    )
    return user


@pytest.fixture
async def second_user(session: AsyncSession) -> User:
    """Создаёт второго пользователя."""
    repo = UserRepository(session)
    user, _ = await repo.get_or_create(
        UserCreateData(
            user_id=2,
            username="second",
            first_name="Second",
            language_code="en",
        )
    )
    return user


@pytest.fixture
async def channel(session: AsyncSession, user: User) -> Channel:
    """Создаёт канал, принадлежащий ``user``."""
    repo = ChannelRepository(session)
    return await repo.create(
        ChannelCreateData(
            channel_id=100,
            channel_name="news",
            user_id=user.id,
        )
    )


@pytest.fixture
async def second_channel(session: AsyncSession, second_user: User) -> Channel:
    """Создаёт канал, принадлежащий ``second_user``."""
    repo = ChannelRepository(session)
    return await repo.create(
        ChannelCreateData(
            channel_id=200,
            channel_name="other",
            user_id=second_user.id,
        )
    )


def create_data_post(
    *,
    user_id: int,
    channel_id: int,
    theme: str = "general",
    content_type: ContentType = ContentType.TEXT,
    text: str | None = "Sample text",
    media_id: str | None = None,
    pub_date: int | None = None,
    spoiler: bool = False,
    msg_delete: int | None = None,
    status: PostStatus = PostStatus.MODER,
) -> PostCreateData:
    return PostCreateData(
        user_id=user_id,
        channel_id=channel_id,
        theme=theme,
        content_type=content_type,
        text=text,
        media_id=media_id,
        pub_date=pub_date,
        spoiler=spoiler,
        msg_delete=msg_delete,
        status=status,
    )


# ---------------------------------------------------------------- create


async def test_create_text_post_success(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    data = create_data_post(
        user_id=user.id,
        channel_id=channel.id,
        theme="news",
        text="Hello world",
    )

    post = await repository.create(data)

    assert post.id is not None
    assert post.user_id == user.id
    assert post.channel_id == channel.id
    assert post.theme == "news"
    assert post.content_type == ContentType.TEXT
    assert post.text == "Hello world"
    assert post.media_id is None
    assert post.status == PostStatus.MODER
    assert post.spoiler is False
    assert post.msg_delete is None

    stored = await session.get(Post, post.id)
    assert stored is not None
    assert stored.text == "Hello world"


async def test_create_photo_post_success(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    data = create_data_post(
        user_id=user.id,
        channel_id=channel.id,
        theme="photos",
        content_type=ContentType.PHOTO,
        text=None,
        media_id="file-id",
        spoiler=True,
        msg_delete=24,
    )

    post = await repository.create(data)

    assert post.content_type == ContentType.PHOTO
    assert post.media_id == "file-id"
    assert post.text is None
    assert post.spoiler is True
    assert post.msg_delete == 24


async def test_create_video_post_success(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    data = create_data_post(
        user_id=user.id,
        channel_id=channel.id,
        content_type=ContentType.VIDEO,
        text=None,
        media_id="video-file-id",
    )

    post = await repository.create(data)
    assert post.content_type == ContentType.VIDEO
    assert post.media_id == "video-file-id"


async def test_create_text_without_text_raises(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    data = create_data_post(
        user_id=user.id,
        channel_id=channel.id,
        content_type=ContentType.TEXT,
        text=None,
    )

    with pytest.raises(PostContentTypeMismatchError):
        await repository.create(data)

    assert await session.scalar(select(Post.id).where(Post.user_id == user.id)) is None


async def test_create_photo_without_media_raises(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    data = create_data_post(
        user_id=user.id,
        channel_id=channel.id,
        content_type=ContentType.PHOTO,
        text=None,
        media_id=None,
    )

    with pytest.raises(PostContentTypeMismatchError):
        await repository.create(data)


async def test_create_post_on_foreign_channel_raises(
    session: AsyncSession,
    user: User,
    second_channel: Channel,
) -> None:
    repository = PostRepository(session)
    data = create_data_post(
        user_id=user.id,
        channel_id=second_channel.id,
        text="Hi",
    )

    with pytest.raises(PostChannelMismatchError):
        await repository.create(data)


# ---------------------------------------------------------------- read


async def test_get_post(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = PostRepository(session)
    created = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, text="Hi")
    )

    fetched = await repository.get(user.id, created.id)
    assert fetched is created

    assert await repository.get(second_user.id, created.id) is None
    assert await repository.get(user.id, 99999) is None


async def test_exists(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = PostRepository(session)

    assert await repository.exists(user.id, 1) is False

    post = await repository.create(create_data_post(user_id=user.id, channel_id=channel.id))

    assert await repository.exists(user.id, post.id) is True
    assert await repository.exists(second_user.id, post.id) is False
    assert await repository.exists(user.id, post.id + 1) is False


# ---------------------------------------------------------------- delete


async def test_delete_post(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = PostRepository(session)
    post = await repository.create(create_data_post(user_id=user.id, channel_id=channel.id))

    # Deletion by another user does not work
    with pytest.raises(PostNotFoundError):
        await repository.delete(second_user.id, post.id)

    # The post still exists
    assert await session.get(Post, post.id) is not None

    # Deletion by owner
    await repository.delete(user.id, post.id)
    await session.flush()
    assert await session.get(Post, post.id) is None

    # Repeated deletion
    with pytest.raises(PostNotFoundError):
        await repository.delete(user.id, post.id)


# ---------------------------------------------------------------- listing


async def test_list_for_user_orders_by_pub_date_desc(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = PostRepository(session)

    # pub_date are unix timestamps; the null one must sort last.
    p_low = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, text="low", pub_date=100)
    )
    p_high = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, text="high", pub_date=200)
    )
    p_null = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, text="null", pub_date=None)
    )
    # Another user's post must not leak in.
    await repository.create(
        create_data_post(
            user_id=second_user.id,
            channel_id=second_channel.id,
            text="other",
            pub_date=999,
        )
    )

    posts = await repository.list_for_user(user.id, limit=10)
    assert [p.id for p in posts] == [p_high.id, p_low.id, p_null.id]


async def test_list_for_user_with_status_filter(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    moder = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, status=PostStatus.MODER)
    )
    await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, status=PostStatus.PUB)
    )

    only_moder = await repository.list_for_user(user.id, status=PostStatus.MODER, limit=10)
    assert [p.id for p in only_moder] == [moder.id]

    only_pub = await repository.list_for_user(user.id, status=PostStatus.PUB, limit=10)
    assert len(only_pub) == 1


async def test_list_for_user_with_channel_filter(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    other_channel_repo = ChannelRepository(session)
    second_own_channel = await other_channel_repo.create(
        ChannelCreateData(
            channel_id=101,
            channel_name="two",
            user_id=user.id,
        )
    )

    in_first = await repository.create(create_data_post(user_id=user.id, channel_id=channel.id))
    in_second = await repository.create(
        create_data_post(user_id=user.id, channel_id=second_own_channel.id)
    )

    only_first = await repository.list_for_user(user.id, channel_id=channel.id, limit=10)
    assert [p.id for p in only_first] == [in_first.id]

    only_second = await repository.list_for_user(
        user.id, channel_id=second_own_channel.id, limit=10
    )
    assert [p.id for p in only_second] == [in_second.id]


async def test_list_for_user_limit_and_offset(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    created = []
    for i in range(3):
        created.append(
            await repository.create(
                create_data_post(
                    user_id=user.id,
                    channel_id=channel.id,
                    pub_date=100 + i,
                )
            )
        )

    # DESC order: 102, 101, 100
    page1 = await repository.list_for_user(user.id, limit=2, offset=0)
    assert [p.id for p in page1] == [created[2].id, created[1].id]

    page2 = await repository.list_for_user(user.id, limit=2, offset=2)
    assert [p.id for p in page2] == [created[0].id]


async def test_count_for_user(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = PostRepository(session)

    assert await repository.count_for_user(user.id) == 0
    assert await repository.count_for_user(second_user.id) == 0

    await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, status=PostStatus.MODER)
    )
    await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, status=PostStatus.PUB)
    )
    await repository.create(
        create_data_post(
            user_id=second_user.id,
            channel_id=second_channel.id,
            status=PostStatus.MODER,
        )
    )

    assert await repository.count_for_user(user.id) == 2
    assert await repository.count_for_user(second_user.id) == 1
    assert await repository.count_for_user(user.id, status=PostStatus.MODER) == 1
    assert await repository.count_for_user(user.id, status=PostStatus.PUB) == 1
    assert await repository.count_for_user(user.id, channel_id=channel.id) == 2


async def test_get_page(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = PostRepository(session)
    created = []
    for i in range(10):
        created.append(
            await repository.create(
                create_data_post(
                    user_id=user.id,
                    channel_id=channel.id,
                    text=f"text {i}",
                    pub_date=100 + i,
                )
            )
        )

    # ORDER BY pub_date DESC: created[9] (109), created[8] (108), ...
    page1 = await repository.get_page(user.id, page=1, per_page=8)
    assert len(page1.items) == 8
    assert page1.total == 10
    assert page1.items[0].id == created[9].id
    assert page1.items[-1].id == created[2].id

    page2 = await repository.get_page(user.id, page=2, per_page=8)
    assert len(page2.items) == 2
    assert page2.total == 10
    assert page2.items[0].id == created[1].id
    assert page2.items[-1].id == created[0].id

    with pytest.raises(ValueError):
        await repository.get_page(user.id, page=0)


async def test_get_page_with_filters(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = PostRepository(session)
    for i in range(4):
        await repository.create(
            create_data_post(
                user_id=user.id,
                channel_id=channel.id,
                status=PostStatus.PUB if i % 2 else PostStatus.MODER,
                pub_date=100 + i,
            )
        )

    page = await repository.get_page(user.id, status=PostStatus.PUB, page=1)
    assert page.total == 2
    assert all(p.status == PostStatus.PUB for p in page.items)


# ---------------------------------------------------------------- update


async def test_update_single_field(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = PostRepository(session)
    post = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, theme="old")
    )

    updated = await repository.update(user.id, post.id, PostUpdateData(theme="new"))

    assert updated is post
    assert updated.theme == "new"
    assert updated.text == "Sample text"  # unchanged


async def test_update_empty_returns_unchanged(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    post = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, theme="t")
    )

    updated = await repository.update(user.id, post.id, PostUpdateData())
    assert updated is post
    assert updated.theme == "t"


async def test_update_not_found_raises(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
) -> None:
    repository = PostRepository(session)
    post = await repository.create(create_data_post(user_id=user.id, channel_id=channel.id))

    with pytest.raises(PostNotFoundError):
        await repository.update(second_user.id, post.id, PostUpdateData(theme="new"))

    with pytest.raises(PostNotFoundError):
        await repository.update(user.id, 99999, PostUpdateData(theme="new"))


async def test_update_clears_nullable_field(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    post = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="text",
            pub_date=12345,
            msg_delete=24,
        )
    )

    updated = await repository.update(
        user.id, post.id, PostUpdateData(pub_date=None, msg_delete=None)
    )

    assert updated.pub_date is None
    assert updated.msg_delete is None
    assert updated.text == "text"  # unchanged


async def test_update_to_photo_without_media_raises(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    post = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, text="text")
    )

    with pytest.raises(PostContentTypeMismatchError):
        await repository.update(user.id, post.id, PostUpdateData(content_type=ContentType.PHOTO))


async def test_update_content_type_and_media_together(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    post = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, text="text")
    )

    updated = await repository.update(
        user.id,
        post.id,
        PostUpdateData(
            content_type=ContentType.PHOTO,
            media_id="file-x",
            text=None,
        ),
    )

    assert updated.content_type == ContentType.PHOTO
    assert updated.media_id == "file-x"
    assert updated.text is None


async def test_update_channel_to_foreign_raises(
    session: AsyncSession,
    user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = PostRepository(session)
    post = await repository.create(create_data_post(user_id=user.id, channel_id=channel.id))

    with pytest.raises(PostChannelMismatchError):
        await repository.update(
            user.id,
            post.id,
            PostUpdateData(channel_id=second_channel.id),
        )


async def test_update_channel_to_own_second_channel(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    channel_repo = ChannelRepository(session)
    second_own = await channel_repo.create(
        ChannelCreateData(channel_id=101, channel_name="two", user_id=user.id)
    )
    repository = PostRepository(session)
    post = await repository.create(create_data_post(user_id=user.id, channel_id=channel.id))

    updated = await repository.update(user.id, post.id, PostUpdateData(channel_id=second_own.id))
    assert updated.channel_id == second_own.id


async def test_update_spoiler_and_status(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    post = await repository.create(
        create_data_post(user_id=user.id, channel_id=channel.id, spoiler=False)
    )

    updated = await repository.update(
        user.id,
        post.id,
        PostUpdateData(spoiler=True, status=PostStatus.PUB),
    )

    assert updated.spoiler is True
    assert updated.status == PostStatus.PUB


# ---------------------------------------------------------------- bulk: archive


async def test_archive_expired(session: AsyncSession, user: User, channel: Channel) -> None:
    repository = PostRepository(session)
    now = 1_000_000

    past_act = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            pub_date=now - 100,
            status=PostStatus.ACT,
        )
    )
    future_act = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            pub_date=now + 100,
            status=PostStatus.ACT,
        )
    )
    past_pub = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            pub_date=now - 100,
            status=PostStatus.PUB,
        )
    )
    no_pub_date_act = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            pub_date=None,
            status=PostStatus.ACT,
        )
    )

    count = await repository.archive_expired(now=now)
    assert count == 1

    # Read raw column values to bypass the identity map / updated_at parsing.
    assert (
        await session.scalar(select(Post.status).where(Post.id == past_act.id)) == PostStatus.ARCH
    )
    assert (
        await session.scalar(select(Post.status).where(Post.id == future_act.id)) == PostStatus.ACT
    )
    assert await session.scalar(select(Post.status).where(Post.id == past_pub.id)) == PostStatus.PUB
    assert (
        await session.scalar(select(Post.status).where(Post.id == no_pub_date_act.id))
        == PostStatus.ACT
    )


async def test_archive_expired_filtered_by_user(
    session: AsyncSession,
    user: User,
    second_user: User,
    channel: Channel,
    second_channel: Channel,
) -> None:
    repository = PostRepository(session)
    now = 1_000_000

    mine = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            pub_date=now - 100,
            status=PostStatus.ACT,
        )
    )
    theirs = await repository.create(
        create_data_post(
            user_id=second_user.id,
            channel_id=second_channel.id,
            pub_date=now - 100,
            status=PostStatus.ACT,
        )
    )

    count = await repository.archive_expired(now=now, user_id=user.id)
    assert count == 1

    assert await session.scalar(select(Post.status).where(Post.id == mine.id)) == PostStatus.ARCH
    assert await session.scalar(select(Post.status).where(Post.id == theirs.id)) == PostStatus.ACT


# ---------------------------------------------------------------- bulk: cleanup


async def test_delete_invalid_moder_by_age(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    """A moderation post older than ``older_than`` is removed.

    The "empty content" branch of ``delete_invalid_moder`` cannot be
    exercised through the public API: ``create``/``update`` validate content
    and the DB CHECK constraint rejects empty rows even on a raw INSERT.
    """
    repository = PostRepository(session)

    old = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="old",
            status=PostStatus.MODER,
        )
    )
    old.created_at = datetime(2020, 1, 1)
    await session.flush()

    fresh = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="fresh",
            status=PostStatus.MODER,
        )
    )

    # Non-moder row must survive regardless of created_at.
    published = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="pub",
            status=PostStatus.PUB,
        )
    )
    published.created_at = datetime(2020, 1, 1)
    await session.flush()

    count = await repository.delete_invalid_moder(older_than=datetime(2021, 1, 1).timestamp())
    assert count == 1

    # Check existence via raw id column, bypassing the identity map.
    assert await session.scalar(select(Post.id).where(Post.id == old.id)) is None
    assert await session.scalar(select(Post.id).where(Post.id == fresh.id)) == fresh.id
    assert await session.scalar(select(Post.id).where(Post.id == published.id)) == published.id


async def test_delete_overdue_published(
    session: AsyncSession, user: User, channel: Channel
) -> None:
    repository = PostRepository(session)
    now = 1_000_000
    retention = 10_000

    old_pub = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="a",
            status=PostStatus.PUB,
            pub_date=now - retention - 1,
        )
    )
    fresh_pub = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="b",
            status=PostStatus.PUB,
            pub_date=now - retention + 1,
        )
    )
    old_ap_pub = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="c",
            status=PostStatus.AP_PUB,
            pub_date=now - retention - 1,
        )
    )
    old_act = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="d",
            status=PostStatus.ACT,
            pub_date=now - retention - 1,
        )
    )
    no_pub_date_pub = await repository.create(
        create_data_post(
            user_id=user.id,
            channel_id=channel.id,
            text="e",
            status=PostStatus.PUB,
            pub_date=None,
        )
    )

    count = await repository.delete_overdue_published(now=now, retention_seconds=retention)
    assert count == 2

    assert await session.scalar(select(Post.id).where(Post.id == old_pub.id)) is None
    assert await session.scalar(select(Post.id).where(Post.id == old_ap_pub.id)) is None
    assert await session.scalar(select(Post.id).where(Post.id == fresh_pub.id)) == fresh_pub.id
    assert await session.scalar(select(Post.id).where(Post.id == old_act.id)) == old_act.id
    assert (
        await session.scalar(select(Post.id).where(Post.id == no_pub_date_pub.id))
        == no_pub_date_pub.id
    )
