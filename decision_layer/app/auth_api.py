from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import firebase_admin
from fastapi import APIRouter, Depends, Header, HTTPException
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import firestore
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthQdrantConfig:
    url: str
    api_key: str
    collection_name: str = "auth_users"


class AuthUser(BaseModel):
    user_id: str
    email: str
    role: str
    name: str


class AuthResponse(BaseModel):
    user: AuthUser
    access_token: str
    token_type: str = "bearer"


class SyncRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    provider: str | None = Field(default=None, max_length=32)


class _QdrantAuthLinkClient:
    _client: QdrantClient | None = None
    _collection_ready = False
    _lock = Lock()

    @classmethod
    def _config(cls) -> AuthQdrantConfig:
        url = (os.getenv("QDRANT_URL") or "").strip().strip('"')
        api_key = (os.getenv("QDRANT_API_KEY") or "").strip().strip('"')
        collection_name = (os.getenv("QDRANT_USERS_COLLECTION") or "auth_users").strip()

        if not url or not api_key:
            raise HTTPException(status_code=503, detail="QDRANT_URL and QDRANT_API_KEY are required")

        return AuthQdrantConfig(url=url, api_key=api_key, collection_name=collection_name)

    @classmethod
    def _get_client(cls) -> QdrantClient:
        if cls._client is None:
            cfg = cls._config()
            cls._client = QdrantClient(url=cfg.url, api_key=cfg.api_key, timeout=float(os.getenv("QDRANT_TIMEOUT_SECONDS", "5")))
        return cls._client

    @classmethod
    def _ensure_collection(cls) -> AuthQdrantConfig:
        cfg = cls._config()
        if cls._collection_ready:
            return cfg

        with cls._lock:
            if cls._collection_ready:
                return cfg

            client = cls._get_client()
            existing = {collection.name for collection in client.get_collections().collections}
            if cfg.collection_name not in existing:
                client.create_collection(
                    collection_name=cfg.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=1,
                        distance=qmodels.Distance.DOT,
                        on_disk=True,
                    ),
                    hnsw_config=qmodels.HnswConfigDiff(
                        m=8,
                        ef_construct=64,
                        on_disk=True,
                    ),
                )

            cls._collection_ready = True
            return cfg

    @classmethod
    def upsert_user(cls, row: dict[str, Any]) -> None:
        cfg = cls._ensure_collection()
        user_id = str(row["user_id"])
        client = cls._get_client()
        try:
            client.upsert(
                collection_name=cfg.collection_name,
                points=[
                    qmodels.PointStruct(
                        id=user_id,
                        vector=[1.0],
                        payload={
                            "user_id": user_id,
                            "email": str(row.get("email") or ""),
                            "role": str(row.get("role") or "reviewer"),
                            "name": str(row.get("name") or "User"),
                            "provider": str(row.get("provider") or "password"),
                        },
                    )
                ],
                wait=False,
            )
        except Exception as exc:
            logger.warning("Skipping Qdrant auth user sync for %s: %s", user_id, exc)


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(status_code=400, detail="Invalid email format")
    return normalized


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization must be Bearer token")

    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


def _admin_email() -> str:
    return (os.getenv("AUTH_ADMIN_EMAIL") or "admin@sentinelai.com").strip().lower()


def _profile_collection_name() -> str:
    return (os.getenv("FIRESTORE_USERS_COLLECTION") or "users").strip()


def _build_firebase_app() -> firebase_admin.App:
    existing = firebase_admin._apps.get("[DEFAULT]")
    if existing is not None:
        return existing

    project_id = (os.getenv("FIREBASE_PROJECT_ID") or "").strip()
    credentials_json = (os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or "").strip()
    credentials_path = (os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or "").strip()

    if credentials_json:
        cred = credentials.Certificate(json.loads(credentials_json))
    elif credentials_path:
        raw_path = Path(credentials_path)
        if raw_path.is_absolute() and raw_path.exists():
            resolved_path = raw_path
        else:
            current = Path(__file__).resolve()
            decision_layer_root = current.parents[1]
            workspace_root = decision_layer_root.parent
            candidates = [
                (Path.cwd() / raw_path).resolve(),
                (workspace_root / raw_path).resolve(),
                (decision_layer_root / raw_path).resolve(),
            ]
            resolved_path = next((candidate for candidate in candidates if candidate.exists()), raw_path)

        cred = credentials.Certificate(str(resolved_path))
    else:
        raise HTTPException(
            status_code=503,
            detail="Firebase credentials are missing. Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH",
        )

    options: dict[str, Any] = {}
    if project_id:
        options["projectId"] = project_id

    return firebase_admin.initialize_app(cred, options=options)


def _firestore_client() -> firestore.Client:
    app = _build_firebase_app()
    return firestore.client(app=app)


def _verify_firebase_token(token: str) -> dict[str, Any]:
    try:
        _build_firebase_app()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Firebase Admin initialization failed") from exc

    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token") from exc


def _provider_from_claims(claims: dict[str, Any], fallback: str | None = None) -> str:
    if fallback:
        return fallback

    firebase_section = claims.get("firebase")
    if isinstance(firebase_section, dict):
        identities = firebase_section.get("identities")
        if isinstance(identities, dict):
            if "google.com" in identities:
                return "google"
            if "password" in identities:
                return "password"

    return "unknown"


def _build_auth_user_from_claims(claims: dict[str, Any], profile: dict[str, Any] | None) -> AuthUser:
    uid = str(claims.get("uid") or "")
    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")

    raw_email = str(claims.get("email") or ((profile or {}).get("email") or ""))
    email = _normalize_email(raw_email)
    name = str((profile or {}).get("name") or claims.get("name") or email.split("@")[0]).strip()
    role = str((profile or {}).get("role") or ("admin" if email == _admin_email() else "reviewer"))

    if role not in {"admin", "reviewer"}:
        role = "reviewer"

    return AuthUser(
        user_id=uid,
        email=email,
        role=role,
        name=name or "User",
    )


def _upsert_firestore_profile(claims: dict[str, Any], body: SyncRequest | None = None) -> AuthUser:
    uid = str(claims.get("uid") or "")
    if not uid:
        raise HTTPException(status_code=401, detail="Token missing uid")

    user = _build_auth_user_from_claims(claims, None)
    provider = _provider_from_claims(claims, body.provider if body is not None else None)

    if body is not None and body.name and body.name.strip():
        user = AuthUser(
            user_id=user.user_id,
            email=user.email,
            role=user.role,
            name=body.name.strip(),
        )

    try:
        db = _firestore_client()
        users = db.collection(_profile_collection_name())
        doc_ref = users.document(uid)
        payload = {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "provider": provider,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        doc_ref.set(payload, merge=True)
    except Exception as exc:
        logger.warning("Firestore profile sync skipped for %s: %s", uid, exc)

    _QdrantAuthLinkClient.upsert_user(
        {
            "user_id": user.user_id,
            "email": user.email,
            "role": user.role,
            "name": user.name,
            "provider": provider,
        }
    )

    return user


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    token = _extract_bearer_token(authorization)
    claims = _verify_firebase_token(token)
    return _upsert_firestore_profile(claims, None)


async def require_admin(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges are required")
    return current_user


@router.post("/sync", response_model=AuthResponse)
async def sync_session(
    body: SyncRequest,
    authorization: str | None = Header(default=None),
) -> AuthResponse:
    token = _extract_bearer_token(authorization)
    claims = _verify_firebase_token(token)
    user = _upsert_firestore_profile(claims, body)
    return AuthResponse(user=user, access_token=token)


@router.get("/me", response_model=AuthUser)
async def me(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return current_user


@router.post("/signup")
async def signup_legacy_disabled() -> dict[str, str]:
    raise HTTPException(status_code=410, detail="Legacy signup disabled. Use Firebase Auth from the frontend")


@router.post("/login")
async def login_legacy_disabled() -> dict[str, str]:
    raise HTTPException(status_code=410, detail="Legacy login disabled. Use Firebase Auth from the frontend")


@router.post("/google")
async def google_legacy_disabled() -> dict[str, str]:
    raise HTTPException(status_code=410, detail="Legacy Google auth disabled. Use Firebase Auth from the frontend")
