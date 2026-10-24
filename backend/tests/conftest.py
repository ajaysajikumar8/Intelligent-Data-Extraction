import os

# Tests sign up many workspaces; none should spend platform Gemini quota unless a test opts in
# by setting trialExtractionsRemaining itself. Must be set before the app reads its settings.
os.environ.setdefault("TRIAL_EXTRACTIONS", "0")
# Every test client shares one IP and the suite signs up dozens of users: keep the signup rate
# limits out of the way (test_email_verification.py patches them down where it tests them) and
# never send real email.
os.environ.setdefault("SIGNUP_LIMIT_PER_IP_PER_HOUR", "100000")
os.environ.setdefault("SIGNUP_LIMIT_PER_DOMAIN_PER_HOUR", "100000")
os.environ.setdefault("TRIAL_DAILY_GRANT_CAP", "100000")
os.environ["RESEND_API_KEY"] = ""

import pytest_asyncio
from app.core.db import connect_db, disconnect_db
from app.core.signup_guard import limiter


@pytest_asyncio.fixture(autouse=True)
async def db_lifespan():
    """
    Automatically connects Prisma DB before each test and disconnects after.
    """
    limiter.reset()
    await connect_db()
    yield
    await disconnect_db()
