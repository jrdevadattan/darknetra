from fastapi import Response

from darknetra.config import Settings


def set_cookies(
    response: Response, settings: Settings, access: str, refresh: str, csrf: str
) -> None:
    secure = settings.env == "production"
    response.set_cookie(
        "darknetra_access",
        access,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api",
        max_age=settings.access_ttl_seconds,
    )
    response.set_cookie(
        "darknetra_refresh",
        refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.refresh_ttl_seconds,
    )
    response.set_cookie(
        "darknetra_csrf",
        csrf,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=settings.refresh_ttl_seconds,
    )


def clear_cookies(response: Response) -> None:
    response.delete_cookie("darknetra_access", path="/api")
    response.delete_cookie("darknetra_refresh", path="/api/v1/auth")
    response.delete_cookie("darknetra_csrf", path="/")
