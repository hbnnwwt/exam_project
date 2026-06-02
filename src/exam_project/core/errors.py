class ProjectError(Exception):
    """Base error with a message suitable for UI display."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class ProjectPackageError(ProjectError):
    """Raised for invalid or corrupted .examproj containers."""


class ProjectValidationError(ProjectError):
    """Raised when project assets are present but inconsistent."""

    def __init__(self, user_message: str, code: str):
        super().__init__(user_message)
        self.code = code
