"""Root router. Sub-routers are tried in the order they are included."""

from aiogram import Router

from bot.handlers import admin, common, errors, fallback, form, membership, profile

router = Router(name="root")
router.include_routers(
    admin.router,
    common.router,
    profile.router,
    form.router,
    membership.router,
    errors.router,
    # The fallback router must stay last: it answers everything nobody else handled.
    fallback.router,
)

__all__ = ["router"]
