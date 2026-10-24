"""Repository for post records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import Select, and_, delete, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Channel,
    ContentType,
    Post,
    PostCreateData,
    PostStatus,
    PostUpdateData,
)
from bot.exceptions import (
    PostChannelMismatchError,
    PostContentTypeMismatchError,
    PostNotFoundError,
)

PER_PAGE = 8


@dataclass(frozen=True, slots=True)
class PostPage:
    items: list[Post]
    total: int


class PostRepository:
    """Data access for :class:`~bot.db.models.Post`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ read

    async def get(self, user_id: int, id: int) -> Post | None:
        """Return the user's post with the given ID, or ``None``."""
        return await self._session.scalar(
            select(Post).where(Post.id == id, Post.user_id == user_id)
        )

    async def exists(self, user_id: int, id: int) -> bool:
        """Return ``True`` if the user has a post with the given ID."""
        statement = select(Post.id).where(Post.id == id, Post.user_id == user_id).limit(1)
        return await self._session.scalar(statement) is not None

    async def list_for_user(
        self,
        user_id: int,
        *,
        status: PostStatus | None = None,
        channel_id: int | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[Post]:
        """Return a page of the user's posts, ordered by publication date.

        Posts without ``pub_date`` (i.e. still in moderation) go last;
        ``id`` provides a stable tiebreaker.
        """
        statement = self._apply_filters(
            select(Post),
            user_id=user_id,
            status=status,
            channel_id=channel_id,
        )
        statement = (
            statement
            # ``coalesce`` gives deterministic NULL ordering across SQLite/PG.
            .order_by(func.coalesce(Post.pub_date, 0).desc(), Post.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(await self._session.scalars(statement))

    async def count_for_user(
        self,
        user_id: int,
        *,
        status: PostStatus | None = None,
        channel_id: int | None = None,
    ) -> int:
        """Return the number of posts matching the given filters."""
        statement = self._apply_filters(
            select(func.count()).select_from(Post),
            user_id=user_id,
            status=status,
            channel_id=channel_id,
        )
        return int(await self._session.scalar(statement) or 0)

    async def get_page(
        self,
        user_id: int,
        *,
        status: PostStatus | None = None,
        channel_id: int | None = None,
        page: int = 1,
        per_page: int = PER_PAGE,
    ) -> PostPage:
        """Return one page of the user's posts together with the total count."""
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")

        offset = (page - 1) * per_page
        items = await self.list_for_user(
            user_id,
            status=status,
            channel_id=channel_id,
            limit=per_page,
            offset=offset,
        )
        total = await self.count_for_user(
            user_id,
            status=status,
            channel_id=channel_id,
        )
        return PostPage(items=items, total=total)

    # ----------------------------------------------------------------- write

    async def create(self, data: PostCreateData) -> Post:
        """Store a new post for the user.

        Raises:
            ``PostChannelMismatchError``: the channel does not belong to the user.
            ``PostContentTypeMismatchError``: content does not match ``content_type``.
        """
        await self._ensure_channel_belongs_to_user(data.user_id, data.channel_id)
        self._ensure_content_matches_type(data.content_type, data.text, data.media_id)

        post = Post(
            user_id=data.user_id,
            channel_id=data.channel_id,
            theme=data.theme,
            content_type=data.content_type,
            text=data.text,
            text_html=data.text_html,
            media_id=data.media_id,
            pub_date=data.pub_date,
            spoiler=data.spoiler,
            msg_delete=data.msg_delete,
            status=data.status,
        )
        self._session.add(post)
        try:
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            # Pre-checks above already cover the common cases; this catches
            # races between the check and the INSERT, plus the composite FK
            # (channel taken by another user in the meantime).
            raise PostContentTypeMismatchError(str(data.content_type)) from exc

        return post

    async def update(
        self,
        user_id: int,
        id: int,
        data: PostUpdateData,
    ) -> Post:
        """Apply a partial update to the user's post.

        Fields that were not set on ``data`` are left untouched; passing
        ``field=None`` clears the column (nullable fields only).

        Raises:
            ``PostNotFoundError``: the post does not exist or belongs to another user.
            ``PostChannelMismatchError``: the new ``channel_id`` does not belong to the user.
            ``PostContentTypeMismatchError``: the resulting content does not match ``content_type``.
        """
        post = await self.get(user_id, id)
        if post is None:
            raise PostNotFoundError(id)

        changes = data.to_changes()
        if not changes:
            return post

        if "channel_id" in changes:
            await self._ensure_channel_belongs_to_user(user_id, changes["channel_id"])

        # Validate the resulting combination, not just the changed fields.
        content_fields = {"content_type", "text", "media_id"}
        if content_fields & changes.keys():
            self._ensure_content_matches_type(
                changes.get("content_type", post.content_type),
                changes.get("text", post.text),
                changes.get("media_id", post.media_id),
            )

        for name, value in changes.items():
            setattr(post, name, value)

        try:
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            raise PostContentTypeMismatchError(str(post.content_type)) from exc

        return post

    async def delete(self, user_id: int, id: int) -> None:
        """Delete the user's post by ID.

        Raises:
            ``PostNotFoundError``: the post does not exist or belongs to another user.
        """
        post = await self.get(user_id, id)
        if post is None:
            raise PostNotFoundError(id)
        await self._session.delete(post)

    # ------------------------------------------------------------- bulk ops

    async def archive_expired(
        self,
        *,
        now: int,
        user_id: int | None = None,
    ) -> int:
        """Archive active posts whose ``pub_date`` is in the past.

        ``now`` is supplied by the caller (unix timestamp) so the repository
        does not decide what "now" is — this keeps tests deterministic.
        ``updated_at`` is set server-side: the column is DateTime, but
        ``now`` is an int (the pub_date unit), so we cannot pass it through.
        Returns the number of affected rows.
        """
        conditions: list[Any] = [
            Post.status == PostStatus.ACT,
            Post.pub_date.is_not(None),
            Post.pub_date < now,
        ]
        if user_id is not None:
            conditions.append(Post.user_id == user_id)

        statement = (
            update(Post)
            .where(*conditions)
            .values(status=PostStatus.ARCH, updated_at=func.now())
            # Bulk UPDATE: keep in-session objects untouched. ``evaluate``
            # would also fail on ``func.now()``.
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)

        # Cast the result to ``CursorResult`` so the type checker knows .rowcount exists.
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    async def delete_invalid_moder(self, *, older_than: datetime) -> int:
        """Delete moderation posts with empty content or older than ``older_than``.

        ``older_than`` is a ``datetime`` because ``created_at`` is a DateTime
        column; passing an int (unix timestamp) would compare a datetime
        string against a number and silently match everything or nothing.
        Returns the number of affected rows.
        """
        statement = (
            delete(Post)
            .where(
                Post.status == PostStatus.MODER,
                or_(
                    and_(
                        Post.content_type == ContentType.TEXT,
                        or_(Post.text.is_(None), Post.text == ""),
                    ),
                    and_(
                        Post.content_type.in_([ContentType.PHOTO, ContentType.VIDEO]),
                        or_(
                            Post.media_id.is_(None),
                            Post.media_id == "",
                        ),
                    ),
                    Post.created_at < older_than,
                ),
            )
            # Bulk DELETE: keep in-session objects untouched.
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)

        # Cast the result to ``CursorResult`` so the type checker knows .rowcount exists.
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    async def delete_overdue_published(
        self,
        *,
        now: int,
        retention_seconds: int,
    ) -> int:
        """Delete published posts older than ``retention_seconds``.

        Uses ``pub_date`` (not ``created_at``): the retention window starts
        when the post is actually published.
        Returns the number of affected rows.
        """
        statement = (
            delete(Post)
            .where(
                Post.status.in_([PostStatus.PUB, PostStatus.AP_PUB]),
                Post.pub_date.is_not(None),
                Post.pub_date < now - retention_seconds,
            )
            # Bulk DELETE: keep in-session objects untouched.
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)

        # Cast the result to ``CursorResult`` so the type checker knows .rowcount exists.
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _apply_filters(
        statement: Select[Any],
        *,
        user_id: int,
        status: PostStatus | None,
        channel_id: int | None,
    ) -> Select[Any]:
        statement = statement.where(Post.user_id == user_id)
        if status is not None:
            statement = statement.where(Post.status == status)
        if channel_id is not None:
            statement = statement.where(Post.channel_id == channel_id)
        return statement

    async def _ensure_channel_belongs_to_user(
        self,
        user_id: int,
        channel_id: int,
    ) -> None:
        """Raise if the channel does not exist or belongs to another user.

        The composite FK on ``posts`` is the hard guarantee; this pre-check
        exists purely to surface a clear domain exception before ``flush``.
        """
        statement = (
            select(Channel.id).where(Channel.id == channel_id, Channel.user_id == user_id).limit(1)
        )
        if await self._session.scalar(statement) is None:
            raise PostChannelMismatchError(channel_id)

    @staticmethod
    def _ensure_content_matches_type(
        content_type: ContentType,
        text: str | None,
        media_id: str | None,
    ) -> None:
        """Raise if the content does not satisfy the declared content type.

        Mirrors ``ck_posts_content_matches_type`` so callers get a domain
        exception instead of an opaque ``IntegrityError``.
        """
        if content_type is ContentType.TEXT and not text:
            raise PostContentTypeMismatchError(content_type.value)
        if content_type in (ContentType.PHOTO, ContentType.VIDEO) and not media_id:
            raise PostContentTypeMismatchError(content_type.value)
