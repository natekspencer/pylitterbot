# pylitterbot

[![PyPI - Version](https://img.shields.io/pypi/v/pylitterbot?style=for-the-badge)](https://pypi.org/project/pylitterbot/)
[![Buy Me A Coffee/Beer](https://img.shields.io/badge/Buy_Me_A_☕/🍺-F16061?style=for-the-badge&logo=ko-fi&logoColor=white&labelColor=grey)](https://ko-fi.com/natekspencer)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor_💜-6f42c1?style=for-the-badge&logo=github&logoColor=white&labelColor=grey)](https://github.com/sponsors/natekspencer)
[![Purchase Litter-Robot](https://img.shields.io/badge/Buy_a_Litter--Robot-Save_$50-lightgrey?style=for-the-badge&labelColor=grey)](https://share.litter-robot.com/x/YZ325z)

[![GitHub License](https://img.shields.io/github/license/natekspencer/pylitterbot?style=flat-square)](LICENSE)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pylitterbot?style=flat-square)](https://pypi.org/project/pylitterbot/)
![Pepy Total Downloads](https://img.shields.io/pepy/dt/pylitterbot?style=flat-square)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pylitterbot?style=flat-square)

Python package for controlling Whisker connected self-cleaning litter boxes and feeders.

This is an unofficial API for controlling various Whisker automated robots. It currently supports Litter-Robot 3 (with connect), Litter-Robot 4 and Feeder-Robot.

## Disclaimer

This API is experimental and was reverse-engineered by monitoring network traffic and decompiling source code from the Whisker app since no public API is currently available at this time. It may cease to work at any time. Use at your own risk.

## Installation

Install using pip

```bash
pip install pylitterbot
```

Alternatively, clone the repository and run

```bash
uv sync
```

## Usage

```python
import asyncio

from pylitterbot import Account

# Set email and password for initial authentication.
username = "Your username"
password = "Your password"


async def main():
    # Create an account.
    account = Account()

    try:
        # Connect to the API and load robots.
        await account.connect(username=username, password=password, load_robots=True)

        # Print robots associated with account.
        print("Robots:")
        for robot in account.robots:
            print(robot)
    finally:
        # Disconnect from the API.
        await account.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

which will output something like:

```
Name: Litter-Robot Name, Serial: LR3C012345, id: a0123b4567cd8e
```

If you only want to discover specific robot families, pass the classes you want
to query when you create the account or when you load robots:

```python
from pylitterbot import Account, LitterRobot4, LitterRobot5

account = Account(robot_types=[LitterRobot4, LitterRobot5])

await account.connect(
  username=username,
  password=password,
  load_robots=True,
)
```

To start a clean cycle

```python
await robot.start_cleaning()
```

If no exception occurred, your Litter-Robot should now perform a clean cycle.

Currently the following methods are available in the Robot class:

- refresh()
- start_cleaning()
- reset_settings()
- set_panel_lockout()
- set_night_light()
- set_power_status()
- set_sleep_mode()
- set_wait_time()
- set_name()
- get_activity_history()
- get_insight()

## Contributing

Thank you for your interest in contributing! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for how to get started.

---

## TODO

- Validate Litter-Robot EVO model data/endpoints if it differs from Litter-Robot 5
- Add support for Litter-Robot 5 cameras

---

## ❤️ Support Me

I maintain this python project in my spare time. If you find it useful, consider supporting development:

- 💜 [Sponsor me on GitHub](https://github.com/sponsors/natekspencer)
- ☕ [Buy me a coffee / beer](https://ko-fi.com/natekspencer)
- 💸 [PayPal (direct support)](https://www.paypal.com/paypalme/natekspencer)
- ⭐ [Star this project](https://github.com/natekspencer/pylitterbot)
- 📦 If you’d like to support in other ways, such as donating hardware for testing, feel free to [reach out to me](https://github.com/natekspencer)

If you don't already own a Litter-Robot, please consider using [my referral link](https://share.litter-robot.com/x/XJAY1D) to purchase your own robot and save $50!

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=natekspencer/pylitterbot)](https://www.star-history.com/#natekspencer/pylitterbot)
