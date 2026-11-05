"""Repository for prompt records."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from bot.db.errors import ConstraintErrorMap, dual_constraint
from bot.db.models import Prompt, PromptCreateData
from bot.db.repositories.base import BaseRepository
from bot.exceptions import InternalError, PromptNameTakenError, PromptNotFoundError

PER_PAGE = 8


@dataclass(frozen=True, slots=True)
class PromptPage:
    items: list[Prompt]
    total: int


def _prompt_create_constraints(data: PromptCreateData) -> ConstraintErrorMap:
    """Constraint map for ``PromptRepository.create``."""
    return dual_constraint(
        "uq_prompts_user_name",
        "unique:prompts.user_id,prompts.name",
        lambda: PromptNameTakenError(data.name),
    )


class PromptRepository(BaseRepository):
    """Data access for :class:`~bot.db.models.Prompt`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.
    """

    async def create(self, data: PromptCreateData) -> Prompt:
        """Store a new prompt for the user.

        Raises:
            ``PromptNameTakenError``: the user already has a prompt with this
                name (including a race on ``uq_prompts_user_name``).
            ``InternalError``: unrecognized ``IntegrityError``.
        """
        await self._ensure_name_is_free(data.user_id, data.name)

        prompt = Prompt(
            user_id=data.user_id,
            name=data.name,
            text=data.text,
        )
        self._session.add(prompt)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise self._translate_integrity_error(exc, _prompt_create_constraints(data)) from exc
        return prompt

    async def get(self, user_id: int, id: int) -> Prompt:
        """Return the user's prompt with the given ID.

        Raises:
            ``PromptNotFoundError``: the prompt does not exist or belongs to
                another user.
        """
        prompt = await self._session.scalar(
            select(Prompt).where(Prompt.id == id, Prompt.user_id == user_id)
        )
        if prompt is None:
            raise PromptNotFoundError(prompt_id=id)
        return prompt

    async def delete(self, user_id: int, id: int) -> None:
        """Delete the user's prompt by ID.

        Raises:
            ``PromptNotFoundError``: the prompt does not exist or belongs to
                another user.
            ``InternalError``: ``IntegrityError`` while flushing the DELETE.
        """
        prompt = await self.get(user_id, id)
        try:
            await self._session.delete(prompt)
            await self._session.flush()
        except IntegrityError as exc:
            raise InternalError() from exc

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int = 0,
    ) -> list[Prompt]:
        """Return a page of the user's prompts, ordered by insertion."""
        statement = (
            select(Prompt)
            .where(Prompt.user_id == user_id)
            .order_by(Prompt.id)
            .limit(limit)
            .offset(offset)
        )
        return list(await self._session.scalars(statement))

    async def count_for_user(self, user_id: int) -> int:
        """Return the number of prompts owned by the user."""
        statement = select(func.count()).select_from(Prompt).where(Prompt.user_id == user_id)
        return int(await self._session.scalar(statement) or 0)

    async def get_page(
        self,
        user_id: int,
        *,
        page: int,
        per_page: int = PER_PAGE,
    ) -> PromptPage:
        """Return one page of the user's prompts together with the total count.

        Raises:
            ``ValueError``: ``page < 1`` (programmer error, not user input).
        """
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")

        offset = (page - 1) * per_page
        items = await self.list_for_user(user_id, limit=per_page, offset=offset)
        total = await self.count_for_user(user_id)
        return PromptPage(items=items, total=total)

    async def _ensure_name_is_free(
        self,
        user_id: int,
        name: str,
    ) -> None:
        statement = select(Prompt.id).where(Prompt.user_id == user_id, Prompt.name == name).limit(1)
        if await self._session.scalar(statement) is not None:
            raise PromptNameTakenError(name)
