import asyncio
import logging
from prisma import Prisma

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("db_seed")

DEFAULT_PLANS = [
    {
        "name": "Free Plan",
        "slug": "free",
        "maxExtractionsPerMonth": 100,
        "maxTemplates": 3,
        "maxWebhooks": 1,
        "maxUsers": 2,
        "priceUsdCents": 0,
        "isActive": True,
    },
    {
        "name": "Pro Plan",
        "slug": "pro",
        "maxExtractionsPerMonth": 5000,
        "maxTemplates": 25,
        "maxWebhooks": 10,
        "maxUsers": 10,
        "priceUsdCents": 4900,
        "isActive": True,
    },
    {
        "name": "Enterprise Plan",
        "slug": "enterprise",
        "maxExtractionsPerMonth": None,
        "maxTemplates": None,
        "maxWebhooks": None,
        "maxUsers": None,
        "priceUsdCents": 19900,
        "isActive": True,
    },
]


async def seed_database() -> None:
    """
    Seed initial required data into PostgreSQL database via Prisma ORM.
    Upserts default billing Plans (free, pro, enterprise).
    """
    db = Prisma()
    await db.connect()
    try:
        logger.info("Starting database seeding...")
        for plan_data in DEFAULT_PLANS:
            plan = await db.plan.upsert(
                where={"slug": plan_data["slug"]},
                data={
                    "create": plan_data,
                    "update": plan_data,
                },
            )
            logger.info("Seeded Plan: %s (ID: %s, Slug: %s)", plan.name, plan.id, plan.slug)
        logger.info("Database seeding completed successfully.")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(seed_database())
