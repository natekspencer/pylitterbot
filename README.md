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
from pylitterbot import Account
username = "Your username"
password = "Your password"
account = Account(username, password)
print("Robots:")
for robot in account.robots:
    print(robot)
```

which will output something like:
```
Name: Litter-Robot Name, Serial: LR3C012345, id: a0123b4567cd8e
```

To start a clean cycle

```python
robot.start_cleaning()
```

If no exception occurred, your Litter-Robot should now perform a clean cycle.

Currently the following methods are available in the Robot class:

* refresh_robot_info()
* start_cleaning()
* reset_settings()
* set_panel_lockout()
* set_night_light()
* set_power_status()
* set_sleep_mode()
* set_wait_time()
* set_robot_name()
* reset_waste_drawer()
* get_robot_activity()
* get_robot_insights()
