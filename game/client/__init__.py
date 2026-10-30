

class SessionAbort(Exception):
    """Raised by a session that cannot start (e.g. co-op host/join failed); main returns to the menus."""
