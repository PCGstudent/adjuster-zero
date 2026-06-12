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

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    import uvicorn

    uvicorn.run("adjuster_zero.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
