"""Repository for prompt records."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Prompt, PromptCreateData
from bot.exceptions import PromptNameTakenError, PromptNotFoundError

PER_PAGE = 8


@dataclass(frozen=True, slots=True)
class PromptPage:
    items: list[Prompt]
    total: int


class PromptRepository:
    """Data access for :class:`~bot.db.models.Prompt`.

    The repository never commits: the transaction is owned by ``DbSessionMiddleware``.

    ``create`` performs a pre-check for name uniqueness and additionally
    translates DB-level ``IntegrityError`` as a race safeguard.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: PromptCreateData) -> Prompt:
        """Store a new prompt for the user.

        Raises:
            PromptNameTakenError: the user already has a prompt with this name,
                or — in the theoretically impossible case — the ``user_id``
                does not exist (FK violation; not expected behind ``UserMiddleware``).
        """
        await self._ensure_name_is_free(data.user_id, data.prompt_name)

        prompt = Prompt(
            user_id=data.user_id,
            prompt_name=data.prompt_name,
            prompt_text=data.prompt_text,
        )
        self._session.add(prompt)
        try:
            # ``flush`` sends the INSERT but does not commit; we only need the
            # generated ``id`` here. A failure leaves the session broken, so we
            # translate the database-level conflict into a domain exception and
            # let ``DbSessionMiddleware`` roll the transaction back.
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - race safeguard
            # Reached when ``(user_id, prompt_name)`` (UNIQUE) collides. A
            # foreign-key violation would land here too, but ``user_id`` is
            # guaranteed to exist by the time the repository is called
            # (UserMiddleware).
            #
            # Race safeguard: ``_ensure_name_is_free`` already rejects taken
            # names, so a concurrent INSERT (two handlers for the same user
            # racing) is the only realistic way to reach this branch.
            raise PromptNameTakenError(data.prompt_name) from exc

        return prompt

    async def get(self, user_id: int, id: int) -> Prompt | None:
        """Return the user's prompt with the given ID, or ``None``."""
        return await self._session.scalar(
            select(Prompt).where(Prompt.id == id, Prompt.user_id == user_id)
        )

    async def delete(self, user_id: int, id: int) -> None:
        """Delete the user's prompt by ID.

        Raises:
            ``PromptNotFoundError``: the prompt does not exist or belongs to another user.
        """
        prompt = await self.get(user_id, id)
        if prompt is None:
            raise PromptNotFoundError(prompt_id=id)

        await self._session.delete(prompt)

    async def exists(self, user_id: int) -> bool:
        """Return ``True`` if the user has at least one prompt."""
        statement = select(Prompt.id).where(Prompt.user_id == user_id).limit(1)
        return await self._session.scalar(statement) is not None

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
        """Return one page of the user's prompts together with the total count."""
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")

        offset = (page - 1) * per_page
        items = await self.list_for_user(user_id, limit=per_page, offset=offset)
        total = await self.count_for_user(user_id)
        return PromptPage(items=items, total=total)

    async def _ensure_name_is_free(
        self,
        user_id: int,
        prompt_name: str,
    ) -> None:
        statement = (
            select(Prompt.id)
            .where(Prompt.user_id == user_id, Prompt.prompt_name == prompt_name)
            .limit(1)
        )
        if await self._session.scalar(statement) is not None:
            raise PromptNameTakenError(prompt_name)
