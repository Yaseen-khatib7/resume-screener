import json
import os
from functools import lru_cache
from typing import Any, Dict

import firebase_admin
from firebase_admin import auth, credentials, firestore


def _load_credentials() -> credentials.Base:
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        if raw.startswith("{"):
            data = json.loads(raw)
        else:
            with open(raw, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        if "private_key" in data:
            data["private_key"] = str(data["private_key"]).replace("\\n", "\n")
        return credentials.Certificate(data)

    return credentials.ApplicationDefault()


@lru_cache(maxsize=1)
def get_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()
    return firebase_admin.initialize_app(_load_credentials())


@lru_cache(maxsize=1)
def get_firestore_client():
    get_firebase_app()
    return firestore.client()


def verify_token(id_token: str) -> Dict[str, Any]:
    get_firebase_app()
    return auth.verify_id_token(id_token)


def get_auth_client():
    get_firebase_app()
    return auth
