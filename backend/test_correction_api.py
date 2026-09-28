import asyncio
from prisma import Prisma
import sys
import os

# Add backend directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def main():
    db = Prisma()
    await db.connect()
    
    workspace = await db.workspace.find_first()
    if not workspace:
        print("No workspace found!")
        return
        
    doc_log = await db.documentlog.create(
        data={
            "workspace": {"connect": {"id": workspace.id}},
            "source": "MANUAL",
            "status": "UNMATCHED",
            "rawInput": "Testing UNMATCHED correction",
        }
    )
    
    print(f"Created UNMATCHED log: {doc_log.id}")
    
    from app.services.extraction_pipeline import validate_correction
    
    try:
        validated_data, errors = validate_correction(None, {"corrected": "data"})
        print("SUCCESS! validate_correction handled None template.")
        print(f"Validated Data: {validated_data}")
        print(f"Errors: {errors}")
    except Exception as e:
        print(f"FAILED! Caught exception: {e}")
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
