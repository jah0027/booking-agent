"""Webhook endpoints"""


from fastapi import APIRouter, Request, HTTPException, Header
import structlog
import json
from app.services.email_service import email_service
from app.config import settings
from app.utils.webhook_signature import verify_svix_signature

logger = structlog.get_logger()
router = APIRouter()

@router.post("/webhooks/email")
async def email_webhook(request: Request, svix_signature: str = Header(None)):
    """
    Inbound email webhook (from Resend or SendGrid)
    """
    try:
        # Get raw JSON payload
        payload_bytes = await request.body()
        payload_str = payload_bytes.decode("utf-8")
        webhook_payload = json.loads(payload_str)


        # Verify webhook signature (Svix)
        secret = settings.webhook_signing_secret or settings.email_webhook_secret
        if not verify_svix_signature(payload_bytes, svix_signature, secret):
            logger.error("webhook_signature_invalid")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        logger.info("webhook_signature_verified")

        # Parse and process the inbound email
        parsed_email = email_service.process_inbound_webhook(webhook_payload)

        # TODO: Route parsed_email to agent for further processing (e.g., create/update conversation)

        logger.info("email_webhook_processed", sender=parsed_email.get("sender_email"), subject=parsed_email.get("subject"))
        return {"status": "processed", "parsed": parsed_email}

    except Exception as e:
        logger.error("email_webhook_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to process email")
