from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from getpass import getpass
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv

from winix import WinixAccount, WinixDevice, WinixDeviceStub
from winix.auth import WinixAuthError, WinixAuthResponse, login, refresh
from winix.driver import WinixDriverError


def _default_env_path() -> Path:
    override = os.getenv("WINIX_ENV_FILE")
    if override:
        return Path(override).expanduser()

    return Path.cwd() / ".env"


def _default_config_path() -> Path:
    override = os.getenv("WINIX_CONFIG_FILE")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "winix" / "config.json"
        return Path.home() / "AppData" / "Roaming" / "winix" / "config.json"

    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "winix" / "config.json"

    return Path.home() / ".config" / "winix" / "config.json"


ENV_PATH = _default_env_path()
load_dotenv(ENV_PATH)

DEFAULT_CONFIG_PATH = _default_config_path()
DEFAULT_OUTPUT = (os.getenv("WINIX_OUTPUT_FORMAT") or "text").strip().lower()


class UserError(Exception):
    pass


class JSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


def _normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("_", " ").split())


def _json_dump(data: Any) -> str:
    return json.dumps(data, cls=JSONEncoder, indent=2, ensure_ascii=False)


def _print_json(data: Any) -> None:
    print(_json_dump(data))


class Configuration:
    exists: bool
    cognito: Optional[WinixAuthResponse]
    devices: List[WinixDeviceStub]

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path).expanduser()
        self.exists = False
        self.cognito = None
        self.devices = []
        self._load_from_disk()

    def device(self, selector: str) -> WinixDeviceStub:
        selector_norm = _normalize(selector)

        if not self.devices:
            raise UserError(
                "No devices are available in the local Winix configuration. "
                "Run `winixctl login` or `winixctl refresh` first."
            )

        if selector_norm.isdigit():
            idx = int(selector_norm)
            if 0 <= idx < len(self.devices):
                return self.devices[idx]

        exact_matches: List[WinixDeviceStub] = []
        partial_matches: List[WinixDeviceStub] = []

        for i, device in enumerate(self.devices):
            mac = _normalize(getattr(device, "mac", ""))
            alias = _normalize(getattr(device, "alias", ""))
            candidates = {str(i), mac, alias}

            if selector_norm in candidates:
                exact_matches.append(device)
                continue

            if selector_norm and (selector_norm in mac or selector_norm in alias):
                partial_matches.append(device)

        if len(exact_matches) == 1:
            return exact_matches[0]

        if len(exact_matches) > 1:
            raise UserError(
                f'Multiple devices exactly matched "{selector}". '
                "Use a more specific index, MAC, or alias."
            )

        if len(partial_matches) == 1:
            return partial_matches[0]

        if len(partial_matches) > 1:
            names = ", ".join(
                f'{getattr(d, "alias", "<no alias>")} ({getattr(d, "mac", "<no mac>")})'
                for d in partial_matches
            )
            raise UserError(
                f'Multiple devices partially matched "{selector}": {names}. '
                "Use a more specific index, MAC, or alias."
            )

        raise UserError(
            f'Could not find device matching "{selector}". '
            "You can use index, MAC, or alias. "
            "View the list of available devices with `winixctl devices`."
        )

    def require_cognito(self) -> WinixAuthResponse:
        if self.cognito is None:
            raise UserError(
                "No Winix authentication is stored locally. "
                "Run `winixctl login` first."
            )
        return self.cognito

    def _load_from_disk(self) -> None:
        if not self.config_path.exists():
            self.exists = False
            self.cognito = None
            self.devices = []
            return

        try:
            js = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise UserError(
                f"Failed to read Winix config file: {self.config_path} :: {exc}"
            ) from exc

        self.exists = True

        cognito_data = js.get("cognito")
        self.cognito = (
            WinixAuthResponse(**cognito_data)
            if isinstance(cognito_data, dict)
            else None
        )

        self.devices = []
        for item in js.get("devices", []):
            if isinstance(item, dict):
                self.devices.append(WinixDeviceStub(**item))

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "cognito": self.cognito,
            "devices": self.devices,
        }

        tmp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        tmp_path.write_text(_json_dump(payload), encoding="utf-8")
        tmp_path.replace(self.config_path)


class Cmd:
    def __init__(self, args: argparse.Namespace, config: Configuration):
        self.args = args
        self.config = config

    @property
    def output(self) -> str:
        return getattr(self.args, "output", "text")

    def active_device(self) -> WinixDeviceStub:
        return self.config.device(self.args.device_selector)

    def active_device_id(self) -> str:
        return self.active_device().id

    def emit(self, data: Any) -> None:
        if self.output == "json":
            _print_json(data)
        else:
            if isinstance(data, str):
                print(data)
            else:
                print(data)


class LoginCmd(Cmd):
    parser_args = {
        "name": "login",
        "help": "Authenticate Winix account",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--username", help="Username (email)", required=False)
        parser.add_argument("--password", help="Password", required=False)
        parser.add_argument(
            "--refresh",
            dest="refresh",
            action="store_true",
            help="Refresh the Winix Cognito token instead of logging in",
        )
        parser.add_argument(
            "--skip-register",
            action="store_true",
            help="Skip register_user after login",
        )

    def execute(self) -> None:
        if getattr(self.args, "refresh", False):
            self._refresh()
        else:
            self._login()

    def _login(self) -> None:
        username = (
            getattr(self.args, "username", None)
            or os.getenv("WINIX_USERNAME")
            or input("Username (email): ").strip()
        )
        password = (
            getattr(self.args, "password", None)
            or os.getenv("WINIX_PASSWORD")
            or getpass("Password: ")
        )

        if not username:
            raise UserError("Username is required.")
        if not password:
            raise UserError("Password is required.")

        try:
            self.config.cognito = login(username, password)
            account = WinixAccount(self.config.cognito.access_token)

            if not getattr(self.args, "skip_register", False):
                account.register_user(username)

            account.check_access_token()
            self.config.devices = account.get_device_info_list()
            self.config.save()
        except (WinixAuthError, WinixDriverError) as exc:
            raise UserError(str(exc)) from exc

        self.emit(
            {
                "ok": True,
                "message": "Authentication successful.",
                "device_count": len(self.config.devices),
                "config_path": str(self.config.config_path),
            }
            if self.output == "json"
            else "Authentication successful."
        )

    def _refresh(self) -> None:
        cognito = self.config.require_cognito()

        try:
            self.config.cognito = refresh(
                user_id=cognito.user_id,
                refresh_token=cognito.refresh_token,
            )

            account = WinixAccount(self.config.cognito.access_token)
            account.check_access_token()
            self.config.devices = account.get_device_info_list()
            self.config.save()
        except (WinixAuthError, WinixDriverError) as exc:
            raise UserError(str(exc)) from exc

        self.emit(
            {
                "ok": True,
                "message": "Token refresh successful.",
                "device_count": len(self.config.devices),
            }
            if self.output == "json"
            else "Token refresh successful."
        )


class DevicesCmd(Cmd):
    parser_args = {
        "name": "devices",
        "help": "List registered Winix devices",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--expose",
            action="store_true",
            help="Expose the full Device ID",
        )

    def execute(self) -> None:
        expose = getattr(self.args, "expose", False)

        devices_out = []
        for i, device in enumerate(self.config.devices):
            raw_id = getattr(device, "id", "")
            masked_id = _mask_device_id(raw_id)

            devices_out.append(
                {
                    "index": i,
                    "default": i == 0,
                    "device_id": raw_id if expose else masked_id,
                    "mac": getattr(device, "mac", ""),
                    "alias": getattr(device, "alias", ""),
                    "location": getattr(device, "location_code", ""),
                }
            )

        if self.output == "json":
            self.emit({"ok": True, "count": len(devices_out), "devices": devices_out})
            return

        print(f"{len(devices_out)} devices:")
        for device in devices_out:
            label = " (default)" if device["default"] else ""
            shown_id = device["device_id"] if expose else device["device_id"] + " (hidden)"
            print(f"Device#{device['index']}{label} ".ljust(50, "-"))
            print(f"{'Device ID':>15} : {shown_id}")
            print(f"{'Mac':>15} : {device['mac']}")
            print(f"{'Alias':>15} : {device['alias']}")
            print(f"{'Location':>15} : {device['location']}")
            print("")

        print("Missing a device? You might need to run refresh.")


class FanCmd(Cmd):
    parser_args = {
        "name": "fan",
        "help": "Fan speed controls",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("level", choices=["low", "medium", "high", "turbo", "sleep"])

    def execute(self) -> None:
        level = self.args.level
        try:
            getattr(WinixDevice(self.active_device_id()), level)()
        except WinixDriverError as exc:
            raise UserError(str(exc)) from exc
        self.emit({"ok": True, "action": "fan", "level": level} if self.output == "json" else "ok")


class PowerCmd(Cmd):
    parser_args = {
        "name": "power",
        "help": "Power controls",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("state", choices=["on", "off"])

    def execute(self) -> None:
        state = self.args.state
        try:
            getattr(WinixDevice(self.active_device_id()), state)()
        except WinixDriverError as exc:
            raise UserError(str(exc)) from exc
        self.emit({"ok": True, "action": "power", "state": state} if self.output == "json" else "ok")


class ModeCmd(Cmd):
    parser_args = {
        "name": "mode",
        "help": "Mode controls",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("state", choices=["auto", "manual"])

    def execute(self) -> None:
        state = self.args.state
        try:
            getattr(WinixDevice(self.active_device_id()), state)()
        except WinixDriverError as exc:
            raise UserError(str(exc)) from exc
        self.emit({"ok": True, "action": "mode", "state": state} if self.output == "json" else "ok")


class PlasmawaveCmd(Cmd):
    parser_args = {
        "name": "plasmawave",
        "help": "Plasmawave controls",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("state", choices=["on", "off"])

    def execute(self) -> None:
        state = self.args.state
        method_name = "plasmawave_on" if state == "on" else "plasmawave_off"
        try:
            getattr(WinixDevice(self.active_device_id()), method_name)()
        except WinixDriverError as exc:
            raise UserError(str(exc)) from exc
        self.emit({"ok": True, "action": "plasmawave", "state": state} if self.output == "json" else "ok")


class RefreshCmd(Cmd):
    parser_args = {
        "name": "refresh",
        "help": "Refresh account device metadata",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        pass

    def execute(self) -> None:
        cognito = self.config.require_cognito()
        try:
            self.config.devices = WinixAccount(cognito.access_token).get_device_info_list()
            self.config.save()
        except WinixDriverError as exc:
            raise UserError(str(exc)) from exc

        self.emit(
            {
                "ok": True,
                "message": "Refresh successful.",
                "device_count": len(self.config.devices),
            }
            if self.output == "json"
            else "Refresh successful."
        )


class StateCmd(Cmd):
    parser_args = {
        "name": "getstate",
        "help": "Get device state",
    }

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        pass

    def execute(self) -> None:
        try:
            status = WinixDevice(self.active_device_id()).get_state()
        except WinixDriverError as exc:
            raise UserError(str(exc)) from exc

        if self.output == "json":
            self.emit({"ok": True, "state": status})
            return

        for field_name, value in status.items():
            print(f"{field_name:>15} : {value}")


def _mask_device_id(device_id: str) -> str:
    if not isinstance(device_id, str) or not device_id or "_" not in device_id:
        return "***hidden***"

    left, right = device_id.split("_", 1)
    return f"{left}_{'*' * len(right)}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Winix Air Purifier Control")
    parser.add_argument(
        "--device",
        "-D",
        help="Device index, MAC, or alias to use",
        default="0",
        dest="device_selector",
    )
    parser.add_argument(
        "--config",
        help="Path to Winix config file",
        default=str(DEFAULT_CONFIG_PATH),
        dest="config_path",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default=DEFAULT_OUTPUT if DEFAULT_OUTPUT in {"text", "json"} else "text",
        help="Output format",
    )

    subparsers = parser.add_subparsers(dest="cmd", required=True)

    commands = {
        cls.parser_args["name"]: cls
        for cls in (
            LoginCmd,
            RefreshCmd,
            DevicesCmd,
            StateCmd,
            FanCmd,
            PowerCmd,
            ModeCmd,
            PlasmawaveCmd,
        )
    }

    for cls in commands.values():
        sub = subparsers.add_parser(**cls.parser_args)
        cls.add_parser(sub)

    parser.set_defaults(_commands=commands)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    commands = getattr(args, "_commands", {})
    cls = commands[args.cmd]

    try:
        config = Configuration(args.config_path)
        cls(args, config=config).execute()
        return 0

    except UserError as exc:
        if getattr(args, "output", "text") == "json":
            _print_json({"ok": False, "error": str(exc)})
        else:
            print(str(exc), file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        if getattr(args, "output", "text") == "json":
            _print_json({"ok": False, "error": "Interrupted"})
        else:
            print("Interrupted", file=sys.stderr)
        return 130

    except Exception as exc:
        message = f"Unexpected error: {exc}"
        if getattr(args, "output", "text") == "json":
            _print_json({"ok": False, "error": message})
        else:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())