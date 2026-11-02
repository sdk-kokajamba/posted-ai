"""Repository for auto prompt records."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    ALL_WEEKDAYS_MASK,
    MINUTES_PER_DAY,
    AutoPost,
    AutoPrompt,
    AutoPromptCreateData,
    AutoPromptUpdateData,
)
from bot.db.ownership import ensure_owned
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
            ``ValueError``: ``text`` is empty or whitespace-only, **or** the
                schedule fields are inconsistent (out-of-range ``day_mask``,
                minutes not in ``[0, 1440)``, ``time_end_min`` set without
                ``time_start_min``, or ``time_end_min == time_start_min``).
            ``AutoPromptAutopostMismatchError``: the auto post does not
                belong to the user.
            ``AutoPromptLimitExceededError``: the auto post already has
                ``MAX_PROMPTS_PER_AUTOPOST`` prompts.
        """
        if not data.text.strip():
            raise ValueError("text must not be empty")

        # Cross-field validation: end without start, start==end, etc.
        self._validate_schedule(data.day_mask, data.time_start_min, data.time_end_min)

        await self._ensure_autopost_belongs_to_user(data.user_id, data.autopost_id)
        # Soft limit: not transactional, so a race between two concurrent
        # ``create`` calls for the same autopost can overshoot by one. Acceptable
        # for now; add a row-level lock on ``autoposts`` if it ever matters.
        if await self.count_for_autopost(data.autopost_id) >= MAX_PROMPTS_PER_AUTOPOST:
            raise AutoPromptLimitExceededError(data.autopost_id)

        prompt = AutoPrompt(
            user_id=data.user_id,
            autopost_id=data.autopost_id,
            text=data.text,
            tags=data.tags,
            day_mask=data.day_mask,
            time_start_min=data.time_start_min,
            time_end_min=data.time_end_min,
        )
        self._session.add(prompt)
        try:
            # ``flush`` sends the INSERT but does not commit; we only need the
            # generated ``id`` here. A failure leaves the session broken, so we
            # translate the DB-level conflict into a domain exception and let
            # ``DbSessionMiddleware`` roll the transaction back.
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            # ``_ensure_autopost_belongs_to_user`` and ``_validate_schedule``
            # already cover the common cases. This catches a concurrent move
            # of the autopost to another user, a schedule CHECK violation that
            # slipped past ``_validate_schedule``, and the user FK if the user
            # was deleted mid-request. All map to
            # ``AutoPromptAutopostMismatchError`` — see the follow-up issue about
            # splitting IntegrityError by constraint name.
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
            ``ValueError``: the resulting schedule is inconsistent — see
                ``_validate_schedule`` for the exact conditions. Raised when
                any of ``day_mask`` / ``time_start_min`` / ``time_end_min``
                is part of ``data``.
        """
        prompt = await self.get(user_id, id)
        if prompt is None:
            raise AutoPromptNotFoundError(id)

        changes = data.to_changes()
        if not changes:
            return prompt

        if "autopost_id" in changes:
            await self._ensure_autopost_belongs_to_user(user_id, changes["autopost_id"])

        # Validate the resulting schedule, not just the changed fields.
        schedule_fields = {"day_mask", "time_start_min", "time_end_min"}
        if schedule_fields & changes.keys():
            self._validate_schedule(
                changes.get("day_mask", prompt.day_mask),
                changes.get("time_start_min", prompt.time_start_min),
                changes.get("time_end_min", prompt.time_end_min),
            )

        for name, value in changes.items():
            setattr(prompt, name, value)

        try:
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race / FK safeguard
            # Same rationale as ``create``: pre-checks already ran against the
            # resulting state, so this branch is a race (autopost moved to
            # another user) or a CHECK violation. Both map to
            # ``AutoPromptAutopostMismatchError`` — see the follow-up issue.
            raise AutoPromptAutopostMismatchError(
                changes.get("autopost_id", prompt.autopost_id),
            ) from exc

        return prompt

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

    # ------------------------------------------------------------------- read

    async def get(self, user_id: int, id: int) -> AutoPrompt | None:
        """Return the user's auto prompt with the given ID, or ``None``."""
        return await self._session.scalar(
            select(AutoPrompt).where(
                AutoPrompt.id == id,
                AutoPrompt.user_id == user_id,
            )
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
    ) -> int:
        """Return the number of prompts for ``user_id``, optionally narrowed to ``autopost_id``."""
        statement = self._apply_filters(
            select(func.count()).select_from(AutoPrompt),
            user_id=user_id,
            autopost_id=autopost_id,
        )
        return int(await self._session.scalar(statement) or 0)

    async def get_page(
        self,
        user_id: int,
        *,
        autopost_id: int | None = None,
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
            limit=per_page,
            offset=offset,
        )
        total = await self.count_for_user(
            user_id,
            autopost_id=autopost_id,
        )
        return AutoPromptPage(items=items, total=total)

    async def get_preview(
        self,
        user_id: int,
        autopost_id: int,
        page: int,
    ) -> AutoPromptPage:
        """Return a one-item page of the user's prompts for ``autopost_id``."""
        return await self.get_page(
            user_id,
            autopost_id=autopost_id,
            page=page,
            per_page=1,
        )

    # --------------------------------------------------------------- helpers

    async def _list(
        self,
        user_id: int,
        *,
        autopost_id: int | None,
        limit: int,
        offset: int,
    ) -> list[AutoPrompt]:
        """Shared page query — ``autopost_id`` may be ``None`` (all autoposts)."""
        statement = self._apply_filters(
            select(AutoPrompt),
            user_id=user_id,
            autopost_id=autopost_id,
        )
        statement = statement.order_by(AutoPrompt.id).limit(limit).offset(offset)
        return list(await self._session.scalars(statement))

    @staticmethod
    def _apply_filters(
        statement: Select[Any],
        *,
        user_id: int,
        autopost_id: int | None,
    ) -> Select[Any]:
        statement = statement.where(AutoPrompt.user_id == user_id)
        if autopost_id is not None:
            statement = statement.where(AutoPrompt.autopost_id == autopost_id)
        return statement

    async def _ensure_autopost_belongs_to_user(
        self,
        user_id: int,
        autopost_id: int,
    ) -> None:
        """Raise if the autopost does not exist or belongs to another user.

        The composite FK on ``autoprompts`` is the hard guarantee; this
        pre-check exists purely to surface a clear domain exception before
        ``flush``. Uses :func:`bot.db.ownership.ensure_owned` — same helper
        as ``PostRepository._ensure_channel_belongs_to_user`` and
        ``AutoPostRepository._ensure_channel_belongs_to_user``.
        """
        await ensure_owned(
            self._session,
            column_id=AutoPost.id,
            column_user_id=AutoPost.user_id,
            pk=autopost_id,
            user_id=user_id,
            error_factory=AutoPromptAutopostMismatchError,
        )

    @staticmethod
    def _validate_schedule(
        day_mask: int | None,
        time_start_min: int | None,
        time_end_min: int | None,
    ) -> None:
        """Mirror the DB CHECK constraints — so callers get a clear
        ``ValueError`` instead of an opaque ``IntegrityError`` from
        ``flush()``."""
        if day_mask is not None and not (0 < day_mask <= ALL_WEEKDAYS_MASK):
            raise ValueError(f"day_mask out of range: {day_mask!r}")

        for name, value in (("time_start_min", time_start_min), ("time_end_min", time_end_min)):
            if value is not None and not (0 <= value < MINUTES_PER_DAY):
                raise ValueError(f"{name} out of range: {value!r}")

        if time_end_min is not None and time_start_min is None:
            raise ValueError("time_end_min set without time_start_min")

        if (
            time_end_min is not None
            and time_start_min is not None
            and time_end_min == time_start_min
        ):
            raise ValueError(
                "time_end_min equals time_start_min; use time_end_min=None for a single point"
            )
