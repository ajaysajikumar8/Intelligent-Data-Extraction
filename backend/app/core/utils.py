from fastapi import HTTPException, UploadFile, status

# Allowed MIME types for file uploads
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
}

# Max file size: 20 MB (Gemini inline data limit)
MAX_FILE_BYTES = 20 * 1024 * 1024

async def validate_and_read_file(file: UploadFile) -> tuple[bytes, str]:
    """
    Read and validate a file upload.
    Checks MIME type against ALLOWED_MIME_TYPES and size against MAX_FILE_BYTES.
    Returns (file_bytes, content_type).
    """
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{content_type}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )
    
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment exceeds 20 MB limit.",
        )
        
    return data, content_type
