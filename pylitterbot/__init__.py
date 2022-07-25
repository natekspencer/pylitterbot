"""pylitterbot module"""
__version__ = "2022.7.1b"

from .account import Account
from .robot import LitterRobot3, LitterRobot4, Robot

__all__ = ["Account", "Robot", "LitterRobot3", "LitterRobot4"]
