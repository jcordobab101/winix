from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Optional

import boto3
from botocore import UNSIGNED
from botocore.client import Config


# Pulled from Winix Home v1.0.8 APK
COGNITO_APP_CLIENT_ID = "14og512b9u20b8vrdm55d8empi"
COGNITO_CLIENT_SECRET_KEY = "k554d4pvgf2n0chbhgtmbe4q0ul4a9flp3pcl6a47ch6rripvvr"
COGNITO_USER_POOL_ID = "us-east-1_Ofd50EosD"
COGNITO_REGION = "us-east-1"


class WinixAuthError(RuntimeError):
    """Raised when Winix Cognito authentication fails."""


@dataclass
class WinixAuthResponse:
    user_id: str
    access_token: str
    refresh_token: str
    id_token: str


def login(username: str, password: str, **kwargs: Any) -> WinixAuthResponse:
    """
    Generate fresh Cognito credentials using SRP authentication.

    This is required for app clients that do not allow USER_PASSWORD_AUTH.
    """
    if not isinstance(username, str) or not username.strip():
        raise WinixAuthError("username must be a non-empty string")

    if not isinstance(password, str) or not password.strip():
        raise WinixAuthError("password must be a non-empty string")

    client_id = kwargs.get("client_id", COGNITO_APP_CLIENT_ID)
    client_secret = kwargs.get("client_secret", COGNITO_CLIENT_SECRET_KEY)
    pool_id = kwargs.get("pool_id", COGNITO_USER_POOL_ID)
    pool_region = kwargs.get("pool_region", COGNITO_REGION)

    try:
        from warrant_lite import WarrantLite
    except Exception as exc:
        raise WinixAuthError(
            "warrant_lite is required for SRP login but is not installed."
        ) from exc

    try:
        wl = WarrantLite(
            username=username.strip(),
            password=password,
            pool_id=pool_id,
            client_id=client_id,
            client_secret=client_secret,
            client=_boto_client(pool_region),
        )

        resp = wl.authenticate_user()
    except Exception as exc:
        raise WinixAuthError(f"Winix SRP login failed: {exc}") from exc

    auth_result = _require_authentication_result(resp, require_refresh=True)
    access_token = auth_result["AccessToken"]
    refresh_token = auth_result["RefreshToken"]
    id_token = auth_result["IdToken"]

    claims = _jwt_claims(access_token)
    user_id = str(claims.get("sub", "")).strip()
    if not user_id:
        raise WinixAuthError("Access token did not contain a valid 'sub' claim")

    return WinixAuthResponse(
        user_id=user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
    )


def refresh(user_id: str, refresh_token: str, **kwargs: Any) -> WinixAuthResponse:
    """
    Refresh Cognito credentials using REFRESH_TOKEN_AUTH.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise WinixAuthError("user_id must be a non-empty string")

    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise WinixAuthError("refresh_token must be a non-empty string")

    client_id = kwargs.get("client_id", COGNITO_APP_CLIENT_ID)
    client_secret = kwargs.get("client_secret", COGNITO_CLIENT_SECRET_KEY)
    pool_region = kwargs.get("pool_region", COGNITO_REGION)

    auth_params = {
        "REFRESH_TOKEN": refresh_token,
        "SECRET_HASH": _secret_hash(
            username=user_id.strip(),
            client_id=client_id,
            client_secret=client_secret,
        ),
    }

    try:
        resp = _boto_client(pool_region).initiate_auth(
            ClientId=client_id,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters=auth_params,
        )
    except Exception as exc:
        raise WinixAuthError(f"Winix refresh failed: {exc}") from exc

    auth_result = _require_authentication_result(resp, require_refresh=False)
    access_token = auth_result["AccessToken"]
    id_token = auth_result["IdToken"]

    return WinixAuthResponse(
        user_id=user_id.strip(),
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
    )


def _require_authentication_result(
    response: dict[str, Any],
    *,
    require_refresh: bool,
) -> dict[str, Any]:
    auth_result = response.get("AuthenticationResult")
    if not isinstance(auth_result, dict):
        raise WinixAuthError("Cognito response missing AuthenticationResult")

    required_keys = ["AccessToken", "IdToken"]
    if require_refresh:
        required_keys.append("RefreshToken")

    missing = [key for key in required_keys if not auth_result.get(key)]
    if missing:
        raise WinixAuthError(
            f"Cognito response missing expected fields: {', '.join(missing)}"
        )

    return auth_result


def _secret_hash(username: str, client_id: str, client_secret: str) -> str:
    """
    Cognito SECRET_HASH = Base64(HMAC_SHA256(client_secret, username + client_id))
    """
    message = f"{username}{client_id}".encode("utf-8")
    key = client_secret.encode("utf-8")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _jwt_claims(token: str) -> dict[str, Any]:
    """
    Decode JWT payload without verifying the signature.
    This is enough to extract stable claims such as 'sub'.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise WinixAuthError("JWT token format is invalid")

        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        claims = json.loads(decoded.decode("utf-8"))

        if not isinstance(claims, dict):
            raise WinixAuthError("JWT payload was not a JSON object")

        return claims
    except Exception as exc:
        if isinstance(exc, WinixAuthError):
            raise
        raise WinixAuthError(f"Failed to decode JWT claims: {exc}") from exc


def _boto_client(region: Optional[str] = None):
    """
    Get an uncredentialed boto Cognito client.
    """
    return boto3.client(
        "cognito-idp",
        config=Config(signature_version=UNSIGNED),
        region_name=region or COGNITO_REGION,
    )