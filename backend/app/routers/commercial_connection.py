"""Admin-only local connection management. No generic provider proxy or dispatch route."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, SecretStr, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db import get_db
from app.deps import require_admin
from app.models import User
from app import commercial_connection as service
from app.commercial_transport import ConnectionError

class SecretRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError:
                # FastAPI's default errors may echo raw input, including credentials.
                raise HTTPException(422, detail="invalid_connection_request") from None
        return safe_handler


router = APIRouter(prefix="/commercial-connection", tags=["commercial-connection"], route_class=SecretRoute)


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int


class ActivationIn(VersionIn):
    activation_code: SecretStr


class CredentialIn(VersionIn):
    # The complete JSON credential document is secret, including validation errors.
    secret_json: SecretStr | None = None


def call(db, fn, *args):
    try:
        return fn(db, *args)
    except ConnectionError as exc:
        db.rollback()
        code = 409 if exc.code in {"version_conflict", "connection_changed"} else 400
        raise HTTPException(code, detail=exc.code) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="version_conflict") from None


@router.get("/status")
def status(db: Session = Depends(get_db), _actor: User = Depends(require_admin)):
    return service.status(db)


@router.post("/activate")
def activate(body: ActivationIn, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    return call(db, service.activate, actor, body.activation_code.get_secret_value(), body.expected_version)


@router.post("/disconnect")
def disconnect(body: VersionIn, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    return call(db, service.disconnect, actor, body.expected_version)


@router.get("/credentials/{key}")
def credential_status(key: str, db: Session = Depends(get_db), _actor: User = Depends(require_admin)):
    return service.credential_status(db, key)


@router.put("/credentials/{key}")
def credential_update(key: str, body: CredentialIn, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    import json
    from app.commercial_transport import MAX_BYTES
    value = None
    if body.secret_json is not None:
        raw = body.secret_json.get_secret_value()
        try:
            if len(raw.encode()) > MAX_BYTES:
                raise ValueError()
            value = json.loads(raw)
            if not isinstance(value, dict) or not value:
                raise ValueError()
        except ValueError:
            raise HTTPException(400, detail="invalid_credential_document") from None
    return call(db, service.set_credential, actor, key, value, body.expected_version)
