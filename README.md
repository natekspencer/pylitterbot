# pylitterbot

Python package for controlling a Litter-Robot Connect self-cleaning litter box

This is an unofficial API for controlling Litter-Robot Connect self-cleaning litter boxes.
The code is based on https://github.com/natekspencer/LitterRobotManager, which in turn was
based on the discussions from https://community.smartthings.com/t/litter-robot-connect/106882
and my own reverse engineering of the API via the android APK.
Session code information is based off of https://github.com/stianaske/pybotvac

## Disclaimer

This API is experimental. Use at your own risk. Feel free to contribute if things are not working.

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

## Support Me

I'm not employed by Litter-Robot, and provide this python package as-is.

If you don't already own a Litter-Robot, please consider using [my referal code](https://www.pntrs.com/t/SENKTkpLSk1DSEtJTklPQ0hKS05HTQ) and get $25 off your own robot (as well as a tip to me in appreciation)!

If you already own a Litter-Robot and/or want to donate to me directly, consider buying me a coffee (or beer) instead by using the link below:

<a href="https://www.buymeacoffee.com/natekspencer" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-blue.png" alt="Buy Me A Coffee" height="41" width="174"></a>
