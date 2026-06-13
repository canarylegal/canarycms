import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth_principal import AuthPrincipal
from app.db import get_db
from app.deps import require_recovery_operator
from app.master_admin import is_reserved_master_login, normalize_master_login
from app.models import User, UserPermissionCategory, UserRole, WebAuthnCredential
from app.schemas import AdminUserCreate, AdminUserPublic, AdminUserSetPassword, AdminUserUpdate, AdminSendPasswordResetResponse
from app.audit import log_event
from app.security import hash_password
from app.password_reset_service import (
    create_password_reset_token,
    password_reset_email_configured,
    send_password_reset_email,
    touch_password_changed,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _clear_user_second_factors(db: Session, user_id: uuid.UUID) -> None:
    db.execute(delete(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id))


def _reject_reserved_login(email: str) -> None:
    if is_reserved_master_login(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That login id is reserved for the master recovery operator.",
        )


@router.get("", response_model=list[AdminUserPublic])
def list_users(
    _operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> list[AdminUserPublic]:
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    return [AdminUserPublic.model_validate(u, from_attributes=True) for u in users]


@router.post("", response_model=AdminUserPublic, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> AdminUserPublic:
    email = normalize_master_login(str(payload.email))
    _reject_reserved_login(email)
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    ini = payload.initials
    taken_i = db.execute(select(User).where(User.initials == ini)).scalar_one_or_none()
    if taken_i:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initials are already in use by another user.",
        )

    category = db.get(UserPermissionCategory, payload.permission_category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission category not found")

    jt = (payload.job_title or "").strip() or None
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        initials=ini,
        job_title=jt,
        role=payload.role,
        is_active=payload.is_active,
        permission_category_id=payload.permission_category_id,
        is_2fa_enabled=False,
        totp_secret=None,
        password_changed_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if operator.is_master_recovery:
        log.info("Master recovery created user %s", user.email)
    log_event(
        db,
        actor_user_id=operator.actor_user_id,
        action="admin.user.create",
        entity_type="user",
        entity_id=str(user.id),
        meta={"email": user.email, "role": user.role.value, "is_active": user.is_active},
    )
    return AdminUserPublic.model_validate(user, from_attributes=True)


@router.patch("/{user_id}", response_model=AdminUserPublic)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> AdminUserPublic:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    data = payload.model_dump(exclude_unset=True)
    fields_set = getattr(payload, "model_fields_set", set()) or set()
    if "initials" in fields_set:
        if payload.initials is not None:
            data["initials"] = payload.initials
        else:
            data.pop("initials", None)
    if "email" in data and data["email"] is not None:
        new_email = normalize_master_login(str(data["email"]))
        _reject_reserved_login(new_email)
        conflict = db.execute(
            select(User).where(User.email == new_email, User.id != user_id)
        ).scalar_one_or_none()
        if conflict:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        data["email"] = new_email
    if "job_title" in data:
        data["job_title"] = (data["job_title"] or "").strip() or None
    if "initials" in data and data["initials"] is not None:
        taken_i = db.execute(
            select(User).where(User.initials == data["initials"], User.id != user_id)
        ).scalar_one_or_none()
        if taken_i:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Initials are already in use by another user.",
            )
    if "permission_category_id" in data and data["permission_category_id"] is not None:
        if db.get(UserPermissionCategory, data["permission_category_id"]) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission category not found")
    final_role = data.get("role", user.role)
    if "permission_category_id" in fields_set:
        final_category_id = data.get("permission_category_id")
    else:
        final_category_id = user.permission_category_id
    if final_role == UserRole.user and final_category_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Staff users must have a permission category assigned.",
        )
    for k, v in data.items():
        setattr(user, k, v)
    user.updated_at = datetime.utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    if operator.is_master_recovery:
        log.info("Master recovery updated user %s", user.email)
    log_event(
        db,
        actor_user_id=operator.actor_user_id,
        action="admin.user.update",
        entity_type="user",
        entity_id=str(user.id),
        meta=payload.model_dump(exclude_unset=True),
    )
    return AdminUserPublic.model_validate(user, from_attributes=True)


@router.post("/{user_id}/set-password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(
    user_id: uuid.UUID,
    payload: AdminUserSetPassword,
    operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> None:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.password_hash = hash_password(payload.password)
    touch_password_changed(user)
    user.totp_secret = None
    user.is_2fa_enabled = False
    _clear_user_second_factors(db, user.id)

    db.add(user)
    db.commit()
    if operator.is_master_recovery:
        log.info("Master recovery reset password for user %s (2FA and passkeys cleared)", user.email)
    log_event(
        db,
        actor_user_id=operator.actor_user_id,
        action="admin.user.set_password",
        entity_type="user",
        entity_id=str(user.id),
    )
    return None


@router.post("/{user_id}/send-password-reset-email", response_model=AdminSendPasswordResetResponse)
def send_user_password_reset_email(
    user_id: uuid.UUID,
    operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> AdminSendPasswordResetResponse:
    if not password_reset_email_configured(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "E-mail is not configured for automated alerts. Configure SMTP or Microsoft Graph under Admin → E-mail, "
                "or set this user's password manually."
            ),
        )
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User account is disabled.")
    if not (user.email or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user has no e-mail address on file.")
    raw = create_password_reset_token(db, user)
    sent = send_password_reset_email(db, user, raw, actor_user_id=operator.actor_user_id)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the password reset e-mail. Check Admin → E-mail alert settings.",
        )
    return AdminSendPasswordResetResponse(
        email_sent=True,
        message=f"Password reset e-mail sent to {user.email}.",
    )


@router.post("/{user_id}/disable-2fa", status_code=status.HTTP_204_NO_CONTENT)
def disable_2fa(
    user_id: uuid.UUID,
    operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> None:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.totp_secret = None
    user.is_2fa_enabled = False
    _clear_user_second_factors(db, user.id)
    user.updated_at = datetime.utcnow()
    db.add(user)
    db.commit()
    if operator.is_master_recovery:
        log.info("Master recovery disabled 2FA/passkeys for user %s", user.email)
    log_event(
        db,
        actor_user_id=operator.actor_user_id,
        action="admin.user.disable_2fa",
        entity_type="user",
        entity_id=str(user.id),
    )
    return None
