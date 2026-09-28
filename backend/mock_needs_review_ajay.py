import asyncio
import json
from prisma import Prisma

async def main():
    db = Prisma()
    await db.connect()
    
    # Get Ajay's workspace
    user = await db.user.find_unique(where={'email': 'ajay@example.com'}, include={'workspace': True})
    if not user or not user.workspace:
        print("User or workspace not found")
        await db.disconnect()
        return
        
    workspace = user.workspace
    
    # Find or create a template for Ajay's workspace
    template = await db.template.find_first(where={'workspaceId': workspace.id})
    if not template:
        print("No template found. Creating one for Ajay's workspace...")
        template = await db.template.create(
            data={
                "workspaceId": workspace.id,
                "name": "Invoice Template",
                "description": "Basic invoice schema",
                "schema": json.dumps({
                    "invoice_number": "STRING",
                    "total_amount": "NUMBER"
                })
            }
        )

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
    print(f"Success! Created NEEDS_REVIEW log: {log.id}")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
