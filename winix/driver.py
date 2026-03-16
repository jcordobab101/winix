from __future__ import annotations

import base64
import dataclasses
import json
import os
from binascii import crc32
from typing import Any, Optional

import requests

from . import auth


DEFAULT_TIMEOUT_SECONDS = float(os.getenv("WINIX_HTTP_TIMEOUT_SECONDS", "15"))


class WinixDriverError(RuntimeError):
    pass


class WinixRequestError(WinixDriverError):
    pass


class WinixResponseError(WinixDriverError):
    pass


@dataclasses.dataclass
class WinixDeviceStub:
    id: str
    mac: str
    alias: str
    location_code: str
    filter_replace_date: str


class WinixAccount:
    def __init__(self, access_token: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        if not isinstance(access_token, str) or not access_token.strip():
            raise WinixDriverError("access_token must be a non-empty string")

        self._uuid: Optional[str] = None
        self.access_token = access_token.strip()
        self.timeout_seconds = float(timeout_seconds)

    def check_access_token(self) -> None:
        payload = {
            "cognitoClientSecretKey": auth.COGNITO_CLIENT_SECRET_KEY,
            "accessToken": self.access_token,
            "uuid": self.get_uuid(),
            "osVersion": "26",
            "mobileLang": "en",
        }

        self._post_json(
            "https://us.mobile.winix-iot.com/checkAccessToken",
            payload,
            rpc_name="checkAccessToken",
        )

    def get_device_info_list(self) -> list[WinixDeviceStub]:
        payload = {
            "accessToken": self.access_token,
            "uuid": self.get_uuid(),
        }

        data = self._post_json(
            "https://us.mobile.winix-iot.com/getDeviceInfoList",
            payload,
            rpc_name="getDeviceInfoList",
        )

        device_info_list = data.get("deviceInfoList")
        if not isinstance(device_info_list, list):
            raise WinixResponseError(
                "getDeviceInfoList response did not include a valid deviceInfoList"
            )

        devices: list[WinixDeviceStub] = []
        for item in device_info_list:
            if not isinstance(item, dict):
                continue

            devices.append(
                WinixDeviceStub(
                    id=str(item.get("deviceId", "") or "").strip(),
                    mac=str(item.get("mac", "") or "").strip(),
                    alias=str(item.get("deviceAlias", "") or "").strip(),
                    location_code=str(item.get("deviceLocCode", "") or "").strip(),
                    filter_replace_date=str(item.get("filterReplaceDate", "") or "").strip(),
                )
            )

        return devices

    def register_user(self, email: str) -> None:
        if not isinstance(email, str) or not email.strip():
            raise WinixDriverError("email must be a non-empty string")

        payload = {
            "cognitoClientSecretKey": auth.COGNITO_CLIENT_SECRET_KEY,
            "accessToken": self.access_token,
            "uuid": self.get_uuid(),
            "email": email.strip(),
            "osType": "android",
            "osVersion": "29",
            "mobileLang": "en",
        }

        self._post_json(
            "https://us.mobile.winix-iot.com/registerUser",
            payload,
            rpc_name="registerUser",
        )

    def get_uuid(self) -> str:
        if self._uuid is None:
            claims = _jwt_claims(self.access_token)
            user_id = str(claims.get("sub", "")).strip()
            if not user_id:
                raise WinixDriverError("Access token does not contain a valid 'sub' claim")

            user_id_bytes = user_id.encode("utf-8")
            p1 = crc32(b"github.com/hfern/winixctl" + user_id_bytes)
            p2 = crc32(b"HGF" + user_id_bytes)
            self._uuid = f"{p1:08x}{p2:08x}"

        return self._uuid

    def _post_json(self, url: str, payload: dict[str, Any], *, rpc_name: str) -> dict[str, Any]:
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise WinixRequestError(f"{rpc_name} request failed: {exc}") from exc

        if response.status_code != 200:
            raise WinixRequestError(
                f"{rpc_name} failed with HTTP {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise WinixResponseError(
                f"{rpc_name} returned invalid JSON: {response.text}"
            ) from exc

        if not isinstance(data, dict):
            raise WinixResponseError(f"{rpc_name} returned unexpected payload type")

        return data


class WinixDevice:
    CTRL_URL = "https://us.api.winix-iot.com/common/control/devices/{deviceid}/A211/{attribute}:{value}"
    STATE_URL = "https://us.api.winix-iot.com/common/event/sttus/devices/{deviceid}"

    category_keys = {
        "power": "A02",
        "mode": "A03",
        "airflow": "A04",
        "aqi": "A05",
        "plasma": "A07",
        "filter_hour": "A21",
        "air_quality": "S07",
        "air_qvalue": "S08",
        "ambient_light": "S14",
    }

    state_keys = {
        "power": {"off": "0", "on": "1"},
        "mode": {"auto": "01", "manual": "02"},
        "airflow": {
            "low": "01",
            "medium": "02",
            "high": "03",
            "turbo": "05",
            "sleep": "06",
        },
        "plasma": {"off": "0", "on": "1"},
        "air_quality": {"good": "01", "fair": "02", "poor": "03"},
    }

    def __init__(self, device_id: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        if not isinstance(device_id, str) or not device_id.strip():
            raise WinixDriverError("device_id must be a non-empty string")

        self.id = device_id.strip()
        self.timeout_seconds = float(timeout_seconds)

    def off(self) -> None:
        self._rpc_attr(self.category_keys["power"], self.state_keys["power"]["off"])

    def on(self) -> None:
        self._rpc_attr(self.category_keys["power"], self.state_keys["power"]["on"])

    def auto(self) -> None:
        self._rpc_attr(self.category_keys["mode"], self.state_keys["mode"]["auto"])

    def manual(self) -> None:
        self._rpc_attr(self.category_keys["mode"], self.state_keys["mode"]["manual"])

    def plasmawave_off(self) -> None:
        self._rpc_attr(self.category_keys["plasma"], self.state_keys["plasma"]["off"])

    def plasmawave_on(self) -> None:
        self._rpc_attr(self.category_keys["plasma"], self.state_keys["plasma"]["on"])

    def low(self) -> None:
        self._rpc_attr(self.category_keys["airflow"], self.state_keys["airflow"]["low"])

    def medium(self) -> None:
        self._rpc_attr(self.category_keys["airflow"], self.state_keys["airflow"]["medium"])

    def high(self) -> None:
        self._rpc_attr(self.category_keys["airflow"], self.state_keys["airflow"]["high"])

    def turbo(self) -> None:
        self._rpc_attr(self.category_keys["airflow"], self.state_keys["airflow"]["turbo"])

    def sleep(self) -> None:
        self._rpc_attr(self.category_keys["airflow"], self.state_keys["airflow"]["sleep"])

    def _rpc_attr(self, attr: str, value: str) -> None:
        url = self.CTRL_URL.format(deviceid=self.id, attribute=attr, value=value)

        try:
            response = requests.get(url, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise WinixRequestError(f"Device control request failed: {exc}") from exc

        if response.status_code != 200:
            raise WinixRequestError(
                f"Device control failed with HTTP {response.status_code}: {response.text}"
            )

    def get_state(self) -> dict[str, Any]:
        url = self.STATE_URL.format(deviceid=self.id)

        try:
            response = requests.get(url, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise WinixRequestError(f"Device state request failed: {exc}") from exc

        if response.status_code != 200:
            raise WinixRequestError(
                f"Device state request failed with HTTP {response.status_code}: {response.text}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise WinixResponseError(f"Device state returned invalid JSON: {response.text}") from exc

        try:
            payload = body["body"]["data"][0]["attributes"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WinixResponseError("Device state returned an unexpected payload shape") from exc

        output: dict[str, Any] = {}

        for payload_key, attribute in payload.items():
            for category, local_key in self.category_keys.items():
                if payload_key != local_key:
                    continue

                if category in self.state_keys:
                    mapped = None
                    for value_key, value in self.state_keys[category].items():
                        if attribute == value:
                            mapped = value_key
                            break
                    output[category] = mapped if mapped is not None else attribute
                else:
                    output[category] = _coerce_numeric(attribute)

        return output


def _jwt_claims(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise WinixDriverError("JWT token format is invalid")

        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        claims = json.loads(decoded.decode("utf-8"))

        if not isinstance(claims, dict):
            raise WinixDriverError("JWT payload is not a JSON object")

        return claims
    except Exception as exc:
        if isinstance(exc, WinixDriverError):
            raise
        raise WinixDriverError(f"Failed to decode JWT claims: {exc}") from exc


def _coerce_numeric(value: Any) -> Any:
    try:
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return int(value)
    except Exception:
        return value