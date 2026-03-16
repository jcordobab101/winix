# winix
Modern Winix Integration
# Winix Controller

This is a Python library for controlling Winix C545 Air Purifier
devices. I reverse-engineered the API calls from the Android app. There
are a few weird idiosyncrasies with the Winix backends.

Included in this package is a CLI program `winixctl`.

## Setup

Install using PyPI: `pip install winix`.
You then have access to the `winix` module in python as well
as the `winixctl` command for shell (which uses the library).

## `winixctl` CLI

```
$ winixctl
usage: winixctl [-h] [--device DEVICE_SELECTOR] {login,refresh,devices,getstate,fan,power,mode,plasmawave} ...

Winix C545 Air Purifier Control

positional arguments:
  {login,refresh,devices,getstate,fan,power,mode,plasmawave}
    login               Authenticate Winix account
    refresh             Refresh account device metadata
    devices             List registered Winix devices
    getstate            Get device state
    fan                 Fan speed controls
    power               Power controls
    mode                Mode controls
    plasmawave          Plasmawave controls

optional arguments:
  -h, --help            show this help message and exit
  --device DEVICE_SELECTOR, -D DEVICE_SELECTOR
                        Device Index/Mac/Alias to use
```

In order to control your device, you first must run `winixctl login`.
this will save a token from the Winix backend in a file on your system
at `~/config/winix/config.json`. It will prompt you for a username
and password. You can use the `--username` and `--password` flags as well.


You can see the devives registered to your winix account
with `winixctl devices`.

    ~/dev/winix(master*) » winixctl devices
    1 devices:
    Device#0 (default) -------------------------------
          Device ID : 123456abcde_********** (hidden)
                Mac : 123456abcde
              Alias : Bedroom
           Location : SROU

    Missing a device? You might need to run refresh.

The last portion of the Device ID is hidden as it can be used to control
the device.

### Multi-device Support

By default the commands will work on the first device you have in your Winix account. If you
have multiple air purifiers, you can specify which device to use by specifying
a value for the top-level `--device` flag (short: `-D`).

You may specify one of:
- The device **index**. Example: `0` _(the default device selector)_.
- The device **mac**. Example: `123456abcde`. Mac values stay the same between device registration.
    If you have a device that you move between Wifi networks frequently then you will want
    to use this.
- The device **alias**. Example: `bedroom`. This is the most human-friendly version.


**Examples**

Turn off the bedroom air purifier _using an alias as the selector_:

    winixctl -D bedroom power off
# Winix Controller

Python library and CLI for controlling **Winix air purifiers** (such as the C545).

This project reverse-engineers the Winix mobile API and provides:

- A Python library
- A command line interface `winixctl`
- Authentication through Winix Cognito
- Multi-device support
- JSON output for automation systems

This tool allows programmatic control of Winix air purifiers without relying on the official mobile application.

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

- Python **3.10+**
- boto3
- requests
- python-dotenv

---

# CLI Usage

```bash
winixctl [-h] [--device DEVICE_SELECTOR] {login,refresh,devices,getstate,fan,power,mode,plasmawave}
```

Commands:

| Command | Description |
|------|-------------|
| `login` | Authenticate Winix account |
| `refresh` | Refresh device metadata |
| `devices` | List registered devices |
| `getstate` | Get device status |
| `fan` | Set fan speed |
| `power` | Turn purifier on/off |
| `mode` | Set auto/manual mode |
| `plasmawave` | Enable/disable Plasmawave |

---

# Authentication

Before using the device you must login.

```bash
winixctl login
```

You will be prompted for:

```
Username (email)
Password
```

The tool retrieves a **Cognito access token** and stores it locally.

---

# Configuration

The token and device metadata are saved locally.

Default location:

```
~/.config/winix/config.json
```

You may override the location with an environment variable:

```
WINIX_CONFIG_FILE
```

Example:

```bash
export WINIX_CONFIG_FILE=/data/winix/config.json
```

---

# Environment Variables

Credentials can also be stored in `.env`.

Example `.env` file:

```
WINIX_USERNAME=user@email.com
WINIX_PASSWORD=yourpassword
WINIX_CONFIG_FILE=/data/winix/config.json
```

This allows **non-interactive authentication**, useful for automation systems.

---

# Listing Devices

```bash
winixctl devices
```

Example output:

```
1 devices:

Device#0 (default)
-----------------------
Device ID : 123456abcde_********
Mac       : 123456abcde
Alias     : Bedroom
Location  : SROU
```

The last part of the device ID is hidden since it can be used to control the device.

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

```
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

```
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
winixctl getstate --output json
```

Example:

```json
{
  "power": "on",
  "mode": "auto",
  "airflow": "medium"
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

Other models using the same cloud API may also work.

---

# Disclaimer

This project is not affiliated with Winix.

The API calls were reverse-engineered from the Winix mobile application.

Use at your own risk.

---

# License

MIT License
