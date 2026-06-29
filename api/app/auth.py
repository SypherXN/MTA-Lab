from fastapi import Depends, Header, HTTPException, status


def require_write_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    from app.config import settings

    if not x_api_key or x_api_key != settings.write_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )


def require_read_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    from app.config import settings

    if not settings.read_auth_enabled:
        return

    if x_api_key in (settings.read_api_key, settings.write_api_key):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing X-API-Key for read access",
    )


WriteKeyDep = Depends(require_write_api_key)
ReadKeyDep = Depends(require_read_api_key)
