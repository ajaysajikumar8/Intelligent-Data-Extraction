import os

# Tests sign up many workspaces; none should spend platform Gemini quota unless a test opts in
# by setting trialExtractionsRemaining itself. Must be set before the app reads its settings.
os.environ.setdefault("TRIAL_EXTRACTIONS", "0")

import pytest_asyncio
from app.core.db import connect_db, disconnect_db


@pytest_asyncio.fixture(autouse=True)
async def db_lifespan():
    """
    Automatically connects Prisma DB before each test and disconnects after.
    """
    await connect_db()
    yield
    await disconnect_db()
