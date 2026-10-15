"""Track users blocking and unblocking the bot in private chats."""

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import KICKED, MEMBER, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated

from bot.db.models import User

logger = logging.getLogger(__name__)

router = Router(name="membership")
router.my_chat_member.filter(F.chat.type == ChatType.PRIVATE)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def on_bot_blocked(event: ChatMemberUpdated, user: User) -> None:
    """The user blocked the bot: remember it so that broadcasts can skip them."""
    user.is_blocked = True
    logger.info("User %s blocked the bot", user.id)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def on_bot_unblocked(event: ChatMemberUpdated, user: User) -> None:
    """The user unblocked the bot."""
    user.is_blocked = False
    logger.info("User %s unblocked the bot", user.id)
