"""User model."""

from sqlalchemy import BigInteger, Boolean, String, false
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """A Telegram user who has interacted with the bot."""

    __tablename__ = "users"

    # The Telegram user ID is the primary key; the database never generates it.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(35))
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    @property
    def full_name(self) -> str:
        """First and last name joined with a space."""
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def __repr__(self) -> str:
        return f"User(id={self.id}, username={self.username!r})"
