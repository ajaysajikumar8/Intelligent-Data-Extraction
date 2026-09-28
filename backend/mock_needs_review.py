import asyncio
import json
from prisma import Prisma

async def main():
    db = Prisma()
    await db.connect()
    
    # Get any workspace
    workspace = await db.workspace.find_first()
    if not workspace:
        print("No workspace found")
        await db.disconnect()
        return
        
    # Get a template
    template = await db.template.find_first()
    if not template:
        print("No template found")
        await db.disconnect()
        return

    # Create a NEEDS_REVIEW log
    log = await db.documentlog.create(
        data={
            "workspaceId": workspace.id,
            "templateId": template.id,
            "source": "MANUAL",
            "status": "NEEDS_REVIEW",
            "fileName": "ambiguous_invoice.pdf",
            "mimeType": "application/pdf",
            "extractedJson": json.dumps({
                "invoice_number": "INV-???",
                "total_amount": 1000
            }),
            "confidenceScores": json.dumps({
                "invoice_number": "Low",
                "total_amount": "High"
            })
        }
    )
    print(f"Created NEEDS_REVIEW log: {log.id}")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
