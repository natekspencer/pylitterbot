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

This is an unofficial API for controlling various Whisker automated robots. It currently supports Litter-Robot 3 (with connect), Litter-Robot 4, Litter-Robot 5 (including the Litter-Robot 5 Pro camera) and Feeder-Robot.

## Disclaimer

This API is experimental and was reverse-engineered by monitoring network traffic and decompiling source code from the Whisker app since no public API is currently available at this time. It may cease to work at any time. Use at your own risk.

## Installation

Install using pip

```bash
pip install pylitterbot
```

To include the MCP server for AI assistant integration:

```bash
pip install pylitterbot[mcp]
```

To include live video streaming for the Litter-Robot 5 Pro camera:

```bash
pip install 'pylitterbot[camera]'
```

Alternatively, clone the repository and run

```bash
uv sync
```

adding `--extra camera` (`uv sync --extra camera`) for live camera video.

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

...

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

### Litter-Robot 5 Pro camera

Litter-Robot 5 Pro robots expose their camera through the `LitterRobot5` class
(`robot.has_camera` is `True`):

```python
from pylitterbot import LitterRobot5

for robot in account.get_robots(LitterRobot5):
    if not robot.has_camera:
        continue

    print(await robot.get_camera_status())  # e.g. "ONLINE"
    print(await robot.get_camera_view())  # "front", "globe" or None if unknown
    if not await robot.set_camera_view("globe"):
        print("Could not switch the camera view")

    # Recorded clips
    for clip in await robot.get_camera_videos(limit=5):
        print(clip.id, clip.event_type, clip.created_at)
```

Clip listings depend on the timezone sent with the request.
`get_camera_videos()` uses the robot's timezone by default; pass `timezone=`
to override it. Listing all clips can take many requests, so avoid calling it
on a polling interval.

Live video uses WebRTC. With the `camera` extra installed, `CameraStream`
receives the video and audio frames in Python:

```python
robot = next((r for r in account.get_robots(LitterRobot5) if r.has_camera), None)

if robot is None:
    print("No Litter-Robot 5 Pro camera on this account")
else:
    async with robot.create_camera_stream() as stream:
        stream.on_video_frame(lambda frame: print(frame.width, frame.height))
        if await stream.wait_for_connection():
            await asyncio.sleep(10)
```

To show the stream in a browser instead (for example, Home Assistant's camera
platform), use `CameraSignalingRelay` from `pylitterbot.camera` to pass the
browser's WebRTC offer and ICE candidates to the camera. Its `start()`
returns once the camera has answered (usually within a few seconds), so keep
accepting the browser's ICE candidates while it runs.

Camera sessions are short-lived. If the camera does not answer an offer
within 10 seconds, the offer is retried once on a fresh session before a
`CameraStreamException` is raised.

## MCP Server

pylitterbot includes an optional [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that lets AI assistants like Claude monitor and control your robots through natural language.

### Installation

```bash
pip install pylitterbot[mcp]
```

### Running

```bash
pylitterbot-mcp
```

or

```bash
python -m pylitterbot.mcp
```

### Claude Desktop configuration

Add this to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "litter-robot": {
      "command": "python",
      "args": ["-m", "pylitterbot.mcp"],
      "env": {
        "LITTER_ROBOT_USERNAME": "your@email.com",
        "LITTER_ROBOT_PASSWORD": "your_password"
      }
    }
  }
}
```

> **Note:** The configuration above stores credentials in plaintext. Ensure
> appropriate file permissions on your config file (owner-only read/write) and
> avoid committing it to version control.

### Available tools

**Status and info:** `get_robots`, `get_robot_status`, `get_activity_history`, `get_insight`, `get_pets`

**Commands:** `start_cleaning`, `reset_robot`, `give_snack`, `set_power_status`

**Settings:** `set_name`, `set_night_light`, `set_night_light_brightness`, `set_night_light_mode`, `set_panel_lockout`, `set_wait_time`, `set_sleep_mode`

**Compound operations** that combine multiple API calls:

| Tool | Description |
|------|-------------|
| `fleet_overview` | Prioritized status across all robots with alerts |
| `clean_all_ready` | Start cleaning on all robots in READY state |
| `sync_settings` | Copy one robot's settings to all others of the same model |
| `pet_usage_report` | Activity data across all robots with pet info |
| `maintenance_forecast` | Estimate when each robot needs emptying |
| `household_digest` | Time-bounded summary of all activity |
| `troubleshooting_report` | Diagnostic bundle for a robot with errors |
| `robot_comparison` | Compare settings and metrics across robots |

## Contributing

Thank you for your interest in contributing! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for how to get started.

---

## ❤️ Support Me

I maintain this python project in my spare time. If you find it useful, consider supporting development:

- 💜 [Sponsor me on GitHub](https://github.com/sponsors/natekspencer)
- ☕ [Buy me a coffee / beer](https://ko-fi.com/natekspencer)
- 💸 [PayPal (direct support)](https://www.paypal.com/paypalme/natekspencer)
- ⭐ [Star this project](https://github.com/natekspencer/pylitterbot)
- 📦 If you’d like to support in other ways, such as donating hardware for testing, feel free to [reach out to me](https://github.com/natekspencer)

If you don't already own a Litter-Robot, please consider using [my referral link](https://share.litter-robot.com/x/xQ4Wnm) to purchase your own robot and save $50!

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=natekspencer/pylitterbot)](https://www.star-history.com/#natekspencer/pylitterbot)
