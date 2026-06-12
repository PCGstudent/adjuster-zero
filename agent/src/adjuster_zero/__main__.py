"""Launcher: `python -m adjuster_zero`.

psycopg's async mode needs a SelectorEventLoop, but Windows defaults to the
ProactorEventLoop and uvicorn builds its loop *before* importing the app — so the
policy must be set here, before uvicorn.run(). On Linux (Cloud Run) this is a
no-op (the default loop already works).
"""

from __future__ import annotations

import asyncio
import os
import sys


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    config = uvicorn.Config("adjuster_zero.main:app", host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        # Force a SelectorEventLoop (psycopg async cannot use Windows' Proactor).
        # Running server.serve() directly bypasses uvicorn's own loop setup.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())
    else:
        server.run()


if __name__ == "__main__":
    main()
