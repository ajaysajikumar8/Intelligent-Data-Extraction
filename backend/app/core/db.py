from prisma import Prisma

# Global async Prisma client instance
db = Prisma()


async def connect_db() -> None:
    """Connect to PostgreSQL database via Prisma ORM."""
    if not db.is_connected():
        await db.connect()


async def disconnect_db() -> None:
    """Disconnect from PostgreSQL database."""
    if db.is_connected():
        await db.disconnect()
