"""DARKNETRA backend."""

import asyncio
import sys

if sys.platform == "win32":
    # psycopg async connections require a selector loop on Python 3.12/Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

__version__ = "0.1.0"
