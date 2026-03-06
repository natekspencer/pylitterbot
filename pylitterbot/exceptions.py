"""pylitterbot exceptions."""


class LitterRobotException(Exception):
    """General Litter-Robot exception."""


class LitterRobotLoginException(LitterRobotException):
    """To indicate there is a login issue."""


class InvalidCommandException(LitterRobotException):
    """To be thrown in the event an invalid command is sent."""


class CameraNotAvailableException(LitterRobotException):
    """Raised when a camera operation is attempted on a robot without a camera."""


class CameraStreamException(LitterRobotException):
    """Raised when a camera streaming operation fails."""


class CameraSessionExpiredException(CameraStreamException):
    """Raised when the camera session token has expired."""
