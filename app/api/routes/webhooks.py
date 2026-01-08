"""Webhook endpoints"""


from fastapi import APIRouter, Request, HTTPException, Header
import structlog
import json
from app.services.email_service import email_service
from app.config import settings
from app.utils.webhook_signature import verify_svix_signature

logger = structlog.get_logger()
router = APIRouter()

from app.agent.orchestrator import booking_agent

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

        # Route parsed_email to agent for further processing (create/update conversation and get reply)
        sender_email = parsed_email.get("sender_email")
        sender_name = parsed_email.get("sender_name")
        message_content = parsed_email.get("text_content") or parsed_email.get("html_content") or ""
        conversation_id = parsed_email["metadata"].get("conversation_id") if parsed_email.get("metadata") else None

        # Determine sender type (simple heuristic: if to band email, treat as venue)
        sender_type = "venue"

        agent_result = await booking_agent.process_message(
            message_content=message_content,
            sender_email=sender_email,
            sender_name=sender_name,
            sender_type=sender_type,
            conversation_id=conversation_id
        )

        agent_reply = agent_result.get("response")

        # Send reply email if agent generated a response
        if agent_reply and sender_email:
            await email_service.send_email(
                to=[sender_email],
                subject=f"Re: {parsed_email.get('subject', 'Your Inquiry')}",
                html=agent_reply,
                text=agent_reply,
                reply_to=parsed_email.get("to", [settings.email_from_address])[0] if parsed_email.get("to") else settings.email_from_address,
                metadata={"conversation_id": agent_result.get("conversation_id", "")}
            )
            logger.info("agent_reply_sent", to=sender_email)

        logger.info("email_webhook_processed", sender=sender_email, subject=parsed_email.get("subject"))
        return {"status": "processed", "parsed": parsed_email, "agent_reply": agent_reply}

    except Exception as e:
        logger.error("email_webhook_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to process email")
