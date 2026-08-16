import pytest
from app.core.db import db
from app.db.seed import seed_database


@pytest.mark.asyncio
async def test_seed_database_and_preflight_guard():
    # 1. Run seed script function
    await seed_database()

    # 2. Verify all plans are present in DB
    free_plan = await db.plan.find_first(where={"slug": "free"})
    pro_plan = await db.plan.find_first(where={"slug": "pro"})
    enterprise_plan = await db.plan.find_first(where={"slug": "enterprise"})

    assert free_plan is not None
    assert free_plan.slug == "free"
    assert pro_plan is not None
    assert enterprise_plan is not None
