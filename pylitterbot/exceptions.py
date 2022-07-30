"""pylitterbot exceptions."""


class LitterRobotException(Exception):
    """General Litter-Robot exception."""


class LitterRobotLoginException(LitterRobotException):
    """To indicate there is a login issue."""


class InvalidCommandException(LitterRobotException):
    """To be thrown in the event an invalid command is sent."""
