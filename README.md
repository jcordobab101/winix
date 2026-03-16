# winix

Modern Winix integration for controlling Winix air purifiers from Python and the command line.

This project reverse-engineers the Winix mobile API and provides:

- A Python library
- A command line interface `winixctl`
- Authentication through Winix Cognito
- Multi-device support
- JSON output for automation systems

This tool allows programmatic control of compatible Winix air purifiers without relying on the official mobile application.

---

# Installation

## Install from GitHub

```bash
pip install git+https://github.com/jcordobab101/winix.git
```

## Install locally

Clone the repository:

```bash
git clone https://github.com/jcordobab101/winix.git
cd winix
pip install -e .
```

---

# Requirements

- Python **3.11+**
- boto3
- requests
- python-dotenv

---

# CLI Usage

```bash
winixctl [-h] [--device DEVICE_SELECTOR] [--config CONFIG_PATH] [--output {text,json}] {login,refresh,devices,getstate,fan,power,mode,plasmawave}
```

Commands:

| Command | Description |
|------|-------------|
| `login` | Authenticate Winix account |
| `refresh` | Refresh device metadata |
| `devices` | List registered devices |
| `getstate` | Get device status |
| `fan` | Set fan speed |
| `power` | Turn purifier on or off |
| `mode` | Set auto or manual mode |
| `plasmawave` | Enable or disable Plasmawave |

---

# Authentication

Before using the device you must log in.

```bash
winixctl login
```

You will be prompted for:

```text
Username (email)
Password
```

The tool retrieves a Cognito access token and stores it locally for later use.

You can also provide credentials directly:

```bash
winixctl login --username you@example.com --password yourpassword
```

---

# Configuration

The token and device metadata are saved locally.

Default location:

```text
F:\vtx\data\winix_config.json
```

You may override the location with:

```text
WINIX_CONFIG_FILE
```

Example:

```bash
set WINIX_CONFIG_FILE=F:\custom\winix_config.json
```

or on Unix-like systems:

```bash
export WINIX_CONFIG_FILE=/data/winix/config.json
```

---

# Environment Variables

Credentials can also be stored in `.env`.

Example:

```text
WINIX_USERNAME=user@email.com
WINIX_PASSWORD=yourpassword
WINIX_CONFIG_FILE=F:\vtx\data\winix_config.json
WINIX_OUTPUT_FORMAT=json
```

This allows non-interactive authentication and easier automation.

---

# Listing Devices

```bash
winixctl devices
```

Example output:

```text
1 devices:

Device#0 (default)
-----------------------
Device ID : 123456abcde_********
Mac       : 123456abcde
Alias     : Bedroom
Location  : SROU
```

The last part of the device ID is hidden because it can be used to control the device.

---

# Selecting a Device

If multiple air purifiers are registered, you can choose one with `--device`.

Possible selectors:

| Selector | Example |
|------|------|
| Index | `0` |
| MAC address | `123456abcde` |
| Alias | `bedroom` |

Example:

```bash
winixctl -D bedroom power off
```

---

# Control Examples

### Turn purifier on

```bash
winixctl power on
```

### Turn purifier off

```bash
winixctl power off
```

### Set fan speed

```bash
winixctl fan turbo
```

Available speeds:

```text
low
medium
high
turbo
sleep
```

### Set operating mode

```bash
winixctl mode auto
```

or

```bash
winixctl mode manual
```

### Plasmawave

```bash
winixctl plasmawave on
```

---

# Get Device Status

```bash
winixctl getstate
```

Example:

```text
power        : on
mode         : auto
airflow      : medium
air_quality  : good
filter_hour  : 241
```

---

# JSON Output

For automation systems you can return JSON:

```bash
winixctl --output json getstate
```

Example:

```json
{
  "ok": true,
  "state": {
    "power": "on",
    "mode": "auto",
    "airflow": "medium"
  }
}
```

---

# Python Library Usage

The package can also be used directly in Python.

```python
from winix import login, WinixAccount, WinixDevice

auth = login("email", "password")

account = WinixAccount(auth.access_token)
devices = account.get_device_info_list()

device = WinixDevice(devices[0].id)
device.turbo()
```

---

# Supported Devices

Tested with:

- Winix **C545**

Other Winix models using the same cloud API may also work.

---

# Disclaimer

This project is not affiliated with Winix.

The API calls were reverse-engineered from the Winix mobile application.

Use at your own risk.

---

# License

MIT License
