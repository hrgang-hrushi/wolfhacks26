"""Top-level ASGI entrypoint for Vercel Python runtime."""
import src.api

app = src.api.app
application = src.api.application
handler = src.api.handler

__all__ = ["app", "application", "handler"]
