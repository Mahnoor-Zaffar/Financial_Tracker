from __future__ import annotations

from flask import abort, request


def clamp_per_page(
    requested_per_page: int | None, default_per_page: int = 20, max_per_page: int = 100
) -> int:
    if requested_per_page is None:
        return default_per_page
    return max(1, min(requested_per_page, max_per_page))


def pagination_from_request(
    default_page: int = 1, default_per_page: int = 20, max_per_page: int = 100
) -> tuple[int, int]:
    page = request.args.get("page", default_page, type=int) or default_page
    per_page = request.args.get("per_page", default_per_page, type=int) or default_per_page
    page = max(page, 1)
    per_page = clamp_per_page(per_page, default_per_page=default_per_page, max_per_page=max_per_page)
    return page, per_page


def get_owned_or_404(model, object_id: int, user_id: int):
    instance = model.query.filter(model.id == object_id, model.user_id == user_id).first()
    if instance is None:
        abort(404)
    return instance
