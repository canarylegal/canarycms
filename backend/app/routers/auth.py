import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.db import get_db
from app.deps import _jwt_raw_from_request, get_current_user
from app.email_integration_settings import build_user_public
from app.models import User, UserRole
from app.org_security import (
    firm_mandates_second_factor,
    firm_password_rotation_policy,
    user_has_any_passkey,
    user_meets_second_factor_policy,
    user_password_change_required,
)
from app.password_reset_service import (
    consume_password_reset_token,
    create_password_reset_token,
    login_access_token,
    password_reset_email_configured,
    send_password_reset_email,
    touch_password_changed,
)
from app.schemas import (
    BootstrapAdminRequest,
    Cancel2FASetupRequest,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    Setup2FAResponse,
    TokenResponse,
    UserDisable2FARequest,
    UserPublic,
    Verify2FARequest,
    Verify2FASessionResponse,
)
from app.security import (
    build_totp_uri,
    create_access_token,
    decode_access_token,
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp,
)
from app.audit import log_event


router = APIRouter(prefix="/auth", tags=["auth"])

_me_bearer = HTTPBearer(auto_error=False)


def _bootstrap_token() -> str:
    token = os.getenv("BOOTSTRAP_ADMIN_TOKEN")
    if not token:
        raise RuntimeError("BOOTSTRAP_ADMIN_TOKEN is not set")
    return token


@router.post("/bootstrap-admin", response_model=UserPublic)
def bootstrap_admin(payload: BootstrapAdminRequest, db: Session = Depends(get_db)) -> UserPublic:
    if payload.token != _bootstrap_token():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token")

    existing = db.execute(select(User).where(User.role == UserRole.admin)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin already exists")

    ini = payload.initials
    taken_i = db.execute(select(User).where(User.initials == ini)).scalar_one_or_none()
    if taken_i:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initials are already in use by another user.",
        )

    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        initials=ini,
        role=UserRole.admin,
        is_active=True,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return build_user_public(user, db)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(select(User).where(User.email == str(payload.email).lower())).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    mandate = firm_mandates_second_factor(db)
    effective_admin = user_effective_admin(user, db)

    if user.is_2fa_enabled:
        if not payload.totp_code or not user.totp_secret:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="2FA required")
        if not verify_totp(secret=user.totp_secret, code=payload.totp_code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")

    # Under mandate: password sign-in always proves MFA via TOTP when enabled. Users with no TOTP and no passkeys
    # receive a restricted JWT (mfa_verified=False) so they can only reach second-factor enrolment routes until
    # they register a passkey or enable authenticator 2FA. Passkey-only accounts cannot get a verified MFA JWT
    # from password alone — they must use passkey sign-in or enable TOTP (e.g. after passkey login).
    mfa_verified = True
    if mandate and not effective_admin:
        db_ok = user_meets_second_factor_policy(db, user.id, is_2fa_enabled=user.is_2fa_enabled)
        if db_ok and not user.is_2fa_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your organisation requires a verified second factor at sign-in. "
                    "This account has a passkey — use Sign in with passkey. "
                    "Password sign-in requires an authenticator app enabled on your account."
                ),
            )
        if not db_ok:
            mfa_verified = False

    token = login_access_token(db, user, mfa_verified=mfa_verified)
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=str(user.id),
        meta={"email": user.email, "password_login_restricted": not mfa_verified},
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserPublic)
def me(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_me_bearer),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    pub = build_user_public(user, db)
    mandate = firm_mandates_second_factor(db)
    rotation_enabled, rotation_days = firm_password_rotation_policy(db)
    if user_effective_admin(user, db) or not mandate:
        sf_ok = True
    else:
        raw = _jwt_raw_from_request(request, creds)
        if raw is None:
            sf_ok = False
        else:
            try:
                tp = decode_access_token(raw)
                sf_ok = tp.mfa_verified is True
            except ValueError:
                sf_ok = False
    pwd_change_required = user_password_change_required(db, user)
    return pub.model_copy(
        update={
            "session_second_factor_verified": sf_ok,
            "organization_requires_password_rotation": rotation_enabled,
            "password_rotation_days": rotation_days,
            "session_password_change_required": pwd_change_required,
        }
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    if not password_reset_email_configured(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="E-mail password reset has not been configured. Please contact your administrator.",
        )
    email = str(payload.email).lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user and user.is_active and (user.email or "").strip():
        raw = create_password_reset_token(db, user)
        send_password_reset_email(db, user, raw)
    return ForgotPasswordResponse(
        message="If an account exists for that e-mail address, a password reset link has been sent.",
    )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> None:
    user = consume_password_reset_token(db, payload.token.strip())
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link.")
    user.password_hash = hash_password(payload.new_password)
    touch_password_changed(user)
    user.totp_secret = None
    user.is_2fa_enabled = False
    db.add(user)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.password.reset",
        entity_type="user",
        entity_id=str(user.id),
    )
    return None


@router.post("/2fa/setup", response_model=Setup2FAResponse)
def setup_2fa(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Setup2FAResponse:
    if user.is_2fa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="2FA already enabled")

    if not user.totp_secret:
        user.totp_secret = generate_totp_secret()
        db.add(user)
        db.commit()
        db.refresh(user)

    issuer = os.getenv("TOTP_ISSUER", "Canary")
    uri = build_totp_uri(secret=user.totp_secret, email=user.email, issuer=issuer)
    return Setup2FAResponse(secret=user.totp_secret, otpauth_uri=uri)


@router.post("/2fa/verify", response_model=Verify2FASessionResponse)
def verify_2fa(
    payload: Verify2FARequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Verify2FASessionResponse:
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA not set up")
    if not verify_totp(secret=user.totp_secret, code=payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    user.is_2fa_enabled = True
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.2fa.enable",
        entity_type="user",
        entity_id=str(user.id),
    )
    access_token = login_access_token(db, user, mfa_verified=True)
    return Verify2FASessionResponse(access_token=access_token, user=build_user_public(user, db))


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_my_2fa(
    payload: UserDisable2FARequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not user.is_2fa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled")
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA secret missing")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password")
    if not verify_totp(secret=user.totp_secret, code=payload.totp_code.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid authenticator code")

    if firm_mandates_second_factor(db) and not user_has_any_passkey(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Your organisation requires two-factor authentication or at least one passkey. "
                "Register a passkey before disabling the authenticator app."
            ),
        )

    user.totp_secret = None
    user.is_2fa_enabled = False
    user.updated_at = datetime.utcnow()
    db.add(user)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.2fa.disable_self",
        entity_type="user",
        entity_id=str(user.id),
    )
    return None


@router.post("/2fa/cancel-setup", status_code=status.HTTP_204_NO_CONTENT)
def cancel_my_2fa_setup(
    payload: Cancel2FASetupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if user.is_2fa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="2FA is already enabled — use disable instead of cancel",
        )
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No 2FA setup in progress")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password")

    if firm_mandates_second_factor(db) and not user_has_any_passkey(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Your organisation requires two-factor authentication or a passkey. "
                "Finish authenticator setup, register a passkey, or ask an admin to adjust the policy."
            ),
        )

    user.totp_secret = None
    user.updated_at = datetime.utcnow()
    db.add(user)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.2fa.cancel_setup",
        entity_type="user",
        entity_id=str(user.id),
    )
    return None


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChangePasswordResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    user.password_hash = hash_password(payload.new_password)
    touch_password_changed(user)

    db.add(user)
    db.commit()
    db.refresh(user)
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.password.change",
        entity_type="user",
        entity_id=str(user.id),
    )
    access_token = login_access_token(db, user, mfa_verified=True)
    return ChangePasswordResponse(access_token=access_token, user=build_user_public(user, db))

