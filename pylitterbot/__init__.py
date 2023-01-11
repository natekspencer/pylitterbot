"""pylitterbot module."""
__version__ = "2023.1.1"

from .account import Account
from .robot import Robot
from .robot.feederrobot import FeederRobot
from .robot.litterrobot import LitterRobot
from .robot.litterrobot3 import LitterRobot3
from .robot.litterrobot4 import LitterRobot4

__all__ = [
    "Account",
    "Robot",
    "LitterRobot",
    "LitterRobot3",
    "LitterRobot4",
    "FeederRobot",
]
