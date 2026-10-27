"""Repository for auto prompt records."""

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AutoPost,
    AutoPrompt,
    AutoPromptCreateData,
    AutoPromptStatus,
    AutoPromptUpdateData,
)
from bot.exceptions import (
    AutoPromptAutopostMismatchError,
    AutoPromptLimitExceededError,
    AutoPromptNotFoundError,
)

PER_PAGE = 8
MAX_PROMPTS_PER_AUTOPOST = 500


@dataclass(frozen=True, slots=True)
class AutoPromptPage:
    items: list[AutoPrompt]
    total: int


class AutoPromptRepository:
    """Data access for :class:`~bot.db.models.AutoPrompt`.

    The repository never commits: the transaction is owned by
    ``DbSessionMiddleware``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ write

    async def create(self, data: AutoPromptCreateData) -> AutoPrompt:
        """Store a new prompt for the user's auto post.

        Raises:
            ``ValueError``: ``prompt_text`` is empty or whitespace-only.
            ``AutoPromptAutopostMismatchError``: the auto post does not
                belong to the user.
            ``AutoPromptLimitExceededError``: the auto post already has
                ``MAX_PROMPTS_PER_AUTOPOST`` prompts.
        """
        if not data.prompt_text.strip():
            raise ValueError("prompt_text must not be empty")

        await self._ensure_autopost_belongs_to_user(data.user_id, data.autopost_id)
        if await self.count_for_autopost(data.autopost_id) >= MAX_PROMPTS_PER_AUTOPOST:
            raise AutoPromptLimitExceededError(data.autopost_id)

        prompt = AutoPrompt(
            user_id=data.user_id,
            autopost_id=data.autopost_id,
            status=data.status,
            req_moder=data.req_moder,
            prompt_text=data.prompt_text,
            tags=data.tags,
            day_pub=data.day_pub,
            time_pub=data.time_pub,
        )
        self._session.add(prompt)
        try:
            # ``flush`` sends the INSERT but does not commit; we only need the
            # generated ``id`` here. A failure leaves the session broken, so we
            # translate the DB-level conflict into a domain exception and let
            # ``DbSessionMiddleware`` roll the transaction back.
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            raise AutoPromptAutopostMismatchError(data.autopost_id) from exc

        return prompt

    async def update(
        self,
        user_id: int,
        id: int,
        data: AutoPromptUpdateData,
    ) -> AutoPrompt:
        """Apply a partial update to the user's auto prompt.

        Fields that were not set on ``data`` are left untouched; passing
        ``field=None`` clears the column (nullable fields only).

        Raises:
            ``AutoPromptNotFoundError``: the prompt does not exist or
                belongs to another user.
            ``AutoPromptAutopostMismatchError``: the new ``autopost_id``
                does not belong to the user.
        """
        prompt = await self.get(user_id, id)
        if prompt is None:
            raise AutoPromptNotFoundError(id)

        changes = data.to_changes()
        if not changes:
            return prompt

        if "autopost_id" in changes:
            await self._ensure_autopost_belongs_to_user(user_id, changes["autopost_id"])

        for name, value in changes.items():
            setattr(prompt, name, value)

        try:
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            raise AutoPromptAutopostMismatchError(
                changes.get("autopost_id", prompt.autopost_id),
            ) from exc

        return prompt

    async def set_require_moderation(
        self,
        user_id: int,
        id: int,
        value: bool,
    ) -> AutoPrompt:
        prompt = await self.get(user_id, id)
        if prompt is None:
            raise AutoPromptNotFoundError(id)
        prompt.req_moder = value
        await self._session.flush()
        return prompt

    async def set_require_moderation_for_autopost(
        self,
        user_id: int,
        autopost_id: int,
        value: bool,
    ) -> int:
        statement = (
            update(AutoPrompt)
            .where(
                AutoPrompt.user_id == user_id,
                AutoPrompt.autopost_id == autopost_id,
            )
            .values(req_moder=value)
            # Bulk UPDATE: keep in-session objects untouched.
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    async def update_status(
        self,
        user_id: int,
        id: int,
        status: AutoPromptStatus,
    ) -> AutoPrompt:
        prompt = await self.get(user_id, id)
        if prompt is None:
            raise AutoPromptNotFoundError(id)
        prompt.status = status
        await self._session.flush()
        return prompt

    async def update_status_for_autopost(
        self,
        autopost_id: int,
        status: AutoPromptStatus,
    ) -> int:
        """Bulk-update the status of every prompt attached to ``autopost_id``.

        No ``user_id`` filter on purpose: called from the scheduler and cron
        paths where the owner is not known up front.
        """
        statement = (
            update(AutoPrompt)
            .where(AutoPrompt.autopost_id == autopost_id)
            .values(status=status)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    async def delete(self, user_id: int, id: int) -> None:
        """Delete the user's auto prompt by ID.

        Raises:
            ``AutoPromptNotFoundError``: the prompt does not exist or
                belongs to another user.
        """
        prompt = await self.get(user_id, id)
        if prompt is None:
            raise AutoPromptNotFoundError(id)
        await self._session.delete(prompt)

    async def delete_for_autopost(self, user_id: int, autopost_id: int) -> int:
        statement = (
            delete(AutoPrompt)
            .where(
                AutoPrompt.user_id == user_id,
                AutoPrompt.autopost_id == autopost_id,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    # ------------------------------------------------------------------- read

    async def get(self, user_id: int, id: int) -> AutoPrompt | None:
        """Return the user's auto prompt with the given ID, or ``None``."""
        return await self._session.scalar(
            select(AutoPrompt).where(
                AutoPrompt.id == id,
                AutoPrompt.user_id == user_id,
            )
        )

    async def get_by_id(self, id: int) -> AutoPrompt | None:
        """Return the prompt with the given ID regardless of owner.

        Intended for internal paths (scheduler, cleanup) where ``id`` comes
        from a trusted source, not from user input.
        """
        return await self._session.scalar(select(AutoPrompt).where(AutoPrompt.id == id))

    async def get_autopost_id(self, user_id: int, id: int) -> int | None:
        statement = (
            select(AutoPrompt.autopost_id)
            .where(AutoPrompt.id == id, AutoPrompt.user_id == user_id)
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def get_text(self, user_id: int, id: int) -> str | None:
        statement = (
            select(AutoPrompt.prompt_text)
            .where(AutoPrompt.id == id, AutoPrompt.user_id == user_id)
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def list_ids_for_autopost(self, autopost_id: int) -> list[int]:
        """Return the IDs of every prompt attached to ``autopost_id``."""
        statement = select(AutoPrompt.id).where(AutoPrompt.autopost_id == autopost_id)
        return list(await self._session.scalars(statement))

    async def list_for_user_and_autopost(
        self,
        user_id: int,
        autopost_id: int,
        *,
        status: AutoPromptStatus | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[AutoPrompt]:
        """Return a page of the user's prompts for a specific auto post."""
        return await self._list(
            user_id,
            autopost_id=autopost_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def count_for_autopost(self, autopost_id: int) -> int:
        """Return the number of prompts attached to ``autopost_id``."""
        statement = (
            select(func.count())
            .select_from(AutoPrompt)
            .where(AutoPrompt.autopost_id == autopost_id)
        )
        return int(await self._session.scalar(statement) or 0)

    async def count_for_user(
        self,
        user_id: int,
        *,
        autopost_id: int | None = None,
        status: AutoPromptStatus | None = None,
    ) -> int:
        """Return the number of prompts matching the given filters."""
        statement = self._apply_filters(
            select(func.count()).select_from(AutoPrompt),
            user_id=user_id,
            autopost_id=autopost_id,
            status=status,
        )
        return int(await self._session.scalar(statement) or 0)

    async def get_page(
        self,
        user_id: int,
        *,
        autopost_id: int | None = None,
        status: AutoPromptStatus | None = None,
        page: int = 1,
        per_page: int = PER_PAGE,
    ) -> AutoPromptPage:
        """Return one page of the user's prompts together with the total."""
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")

        offset = (page - 1) * per_page
        items = await self._list(
            user_id,
            autopost_id=autopost_id,
            status=status,
            limit=per_page,
            offset=offset,
        )
        total = await self.count_for_user(
            user_id,
            autopost_id=autopost_id,
            status=status,
        )
        return AutoPromptPage(items=items, total=total)

    async def get_preview(
        self,
        user_id: int,
        autopost_id: int,
        page: int,
    ) -> AutoPromptPage:
        """Return a one-item preview page of active prompts for an auto post."""
        return await self.get_page(
            user_id,
            autopost_id=autopost_id,
            status=AutoPromptStatus.ACT,
            page=page,
            per_page=1,
        )

    async def exists(self, user_id: int, id: int) -> bool:
        """Return ``True`` if the user has an auto prompt with the given ID."""
        statement = (
            select(AutoPrompt.id).where(AutoPrompt.id == id, AutoPrompt.user_id == user_id).limit(1)
        )
        return await self._session.scalar(statement) is not None

    # ------------------------------------------------------------- bulk ops

    async def delete_stale_moder(
        self,
        *,
        user_id: int | None = None,
        autopost_id: int | None = None,
    ) -> int:
        """Delete auto prompts stuck in ``AutoPostStatus.MODER``.

        ``user_id`` / ``autopost_id`` optionally narrow the scope. Returns
        the number of affected rows. Without filters the deletion is global
        — intended for cron cleanup.
        """
        statement = delete(AutoPrompt).where(AutoPrompt.status == AutoPromptStatus.MODER)
        if user_id is not None:
            statement = statement.where(AutoPrompt.user_id == user_id)
        if autopost_id is not None:
            statement = statement.where(AutoPrompt.autopost_id == autopost_id)
        statement = statement.execution_options(synchronize_session=False)

        result = await self._session.execute(statement)
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    async def delete_invalid(
        self,
        *,
        user_id: int | None = None,
        autopost_id: int | None = None,
    ) -> int:
        """Delete auto prompts with empty ``prompt_text``.

        ``day_pub`` and ``time_pub`` are optional (nullable) and their
        absence is not a validity violation, so they are not checked here.
        Returns the number of affected rows.
        """
        statement = delete(AutoPrompt).where(
            or_(
                AutoPrompt.prompt_text.is_(None),
                AutoPrompt.prompt_text == "",
            ),
        )
        if user_id is not None:
            statement = statement.where(AutoPrompt.user_id == user_id)
        if autopost_id is not None:
            statement = statement.where(AutoPrompt.autopost_id == autopost_id)
        statement = statement.execution_options(synchronize_session=False)

        result = await self._session.execute(statement)
        result = cast("CursorResult[Any]", result)
        return result.rowcount or 0

    # --------------------------------------------------------------- helpers

    async def _list(
        self,
        user_id: int,
        *,
        autopost_id: int | None,
        status: AutoPromptStatus | None,
        limit: int,
        offset: int,
    ) -> list[AutoPrompt]:
        """Shared page query — ``autopost_id`` may be ``None`` (all autoposts)."""
        statement = self._apply_filters(
            select(AutoPrompt),
            user_id=user_id,
            autopost_id=autopost_id,
            status=status,
        )
        statement = statement.order_by(AutoPrompt.id).limit(limit).offset(offset)
        return list(await self._session.scalars(statement))

    @staticmethod
    def _apply_filters(
        statement: Select[Any],
        *,
        user_id: int,
        autopost_id: int | None,
        status: AutoPromptStatus | None,
    ) -> Select[Any]:
        statement = statement.where(AutoPrompt.user_id == user_id)
        if autopost_id is not None:
            statement = statement.where(AutoPrompt.autopost_id == autopost_id)
        if status is not None:
            statement = statement.where(AutoPrompt.status == status)
        return statement

    async def _ensure_autopost_belongs_to_user(
        self,
        user_id: int,
        autopost_id: int,
    ) -> None:
        """Raise if the autopost does not exist or belongs to another user.

        The composite FK on ``autoprompts`` is the hard guarantee; this
        pre-check exists purely to surface a clear domain exception before
        ``flush`` — same pattern as ``_ensure_channel_belongs_to_user`` in
        ``PostRepository`` and ``AutoPostRepository``.
        """
        statement = (
            select(AutoPost.id)
            .where(AutoPost.id == autopost_id, AutoPost.user_id == user_id)
            .limit(1)
        )
        if await self._session.scalar(statement) is None:
            raise AutoPromptAutopostMismatchError(autopost_id)
