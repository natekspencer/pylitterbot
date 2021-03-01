import pkg_resources

try:
    __version__ = pkg_resources.get_distribution("pylitterbot").version
except Exception:  # pragma: no cover
    __version__ = "unknown"
