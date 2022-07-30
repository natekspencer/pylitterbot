[![pypi](https://img.shields.io/pypi/v/pylitterbot?style=for-the-badge)](https://pypi.org/project/pylitterbot)
[![downloads](https://img.shields.io/pypi/dm/pylitterbot?style=for-the-badge)](https://pypi.org/project/pylitterbot)
[![Buy Me A Coffee/Beer](https://img.shields.io/badge/Buy_Me_A_☕/🍺-F16061?style=for-the-badge&logo=ko-fi&logoColor=white&labelColor=grey)](https://ko-fi.com/natekspencer)
[![Purchase Litter-Robot](https://img.shields.io/badge/Buy_a_Litter--Robot-Save_$25-lightgrey?style=for-the-badge&labelColor=grey)](https://www.gopjn.com/t/SENKTktMR0lDSEtJTklPQ0hKS05HTQ)

# pylitterbot

Python package for controlling Whisker automatic robots.

This is an unofficial API for controlling various Whisker automated robots. It currently supports Litter-Robot 3, Litter-Robot 4 and Feeder-Robot.

## Disclaimer

This API is experimental and was reverse-engineered by monitoring network traffic and decompiling source code from the Whisker app since no public API is currently available at this time. It may cease to work at any time. Use at your own risk.

## Installation

Install using pip

```bash
pip install pylitterbot
```

Alternatively, clone the repository and run

```bash
python setup.py install
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
- reset_waste_drawer()
- get_activity_history()
- get_insight()

---

## TODO

- Improve support for Litter-Robot 4
- Improve support for Feeder-Robot

---

## Support Me

I'm not employed by Whisker and provide this python package as-is.

If you don't already own a Litter-Robot, please consider using [my affiliate link](https://www.gopjn.com/t/SENKTktMR0lDSEtJTklPQ0hKS05HTQ) to purchase your own robot and save $25!

If you already own a Litter-Robot and/or want to donate to me directly, consider buying me a coffee (or beer) instead by using the link below:

<a href='https://ko-fi.com/natekspencer' target='_blank'><img height='35' style='border:0px;height:46px;' src='https://az743702.vo.msecnd.net/cdn/kofi3.png?v=0' border='0' alt='Buy Me a Coffee at ko-fi.com' />
