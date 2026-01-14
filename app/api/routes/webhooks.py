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
async def email_webhook(request: Request, svix_signature: str = Header(None, alias="Svix-Signature")):
    """
    Inbound email webhook (from Resend or SendGrid)
    """
    logger.info("webhook_request_received")
    try:

        # Get raw JSON payload
        payload_bytes = await request.body()
        payload_str = payload_bytes.decode("utf-8")
        webhook_payload = json.loads(payload_str)

        # Verify webhook signature (Svix)
        secret = settings.webhook_signing_secret or settings.email_webhook_secret
        if not verify_svix_signature(payload_bytes, dict(request.headers), secret):
            logger.error("webhook_signature_invalid")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        logger.info("webhook_signature_verified")

        # Parse and process the inbound email
        parsed_email = email_service.process_inbound_webhook(webhook_payload)

        # If email.received, fetch full email content using Resend REST API
        if parsed_email.get("event_type") == "email_received":
            # Use only the email_id (UUID) for the Resend API call
            email_id = parsed_email.get("email_id")
            full_email = None
            if email_id:
                try:
                    import httpx
                    api_key = settings.resend_api_key
                    url = f"https://api.resend.com/emails/{email_id}"
                    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(url, headers=headers)
                        resp.raise_for_status()
                        full_email = resp.json()
                    # full_email should have 'text', 'html', etc.
                    parsed_email["text_content"] = full_email.get("text")
                    parsed_email["html_content"] = full_email.get("html")
                except Exception as e:
                    logger.error("Failed to fetch full email content from Resend API", error=str(e), email_id=email_id)

        # Route parsed_email to agent for further processing (create/update conversation and get reply)
        sender_email = parsed_email.get("sender_email")
        sender_name = parsed_email.get("sender_name")
        text_content = parsed_email.get("text_content")
        html_content = parsed_email.get("html_content")
        message_content = text_content or html_content or ""
        conversation_id = parsed_email["metadata"].get("conversation_id") if parsed_email.get("metadata") else None

        # Log the extracted message body for debugging
        logger.info(
            "webhook_message_content_debug",
            sender_email=sender_email,
            sender_name=sender_name,
            text_content=text_content,
            html_content=html_content,
            message_content=message_content
        )

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
            # Always use message_id from inbound email for threading
            in_reply_to = None
            references = None
            # Try to get message_id from both data/message_id and metadata
            if "message_id" in parsed_email:
                in_reply_to = parsed_email["message_id"]
                references = parsed_email["message_id"]
            elif parsed_email.get("metadata") and parsed_email["metadata"].get("message_id"):
                in_reply_to = parsed_email["metadata"]["message_id"]
                references = parsed_email["metadata"]["message_id"]
            await email_service.send_email(
                to=[sender_email],
                subject=f"Re: {parsed_email.get('subject', 'Your Inquiry')}",
                html=agent_reply,
                text=agent_reply,
                reply_to=parsed_email.get("to", [settings.email_from_address])[0] if parsed_email.get("to") else settings.email_from_address,
                metadata={
                    "conversation_id": agent_result.get("conversation_id", "")
                },
                in_reply_to=in_reply_to,
                references=references
            )
            logger.info("agent_reply_sent", to=sender_email, in_reply_to=in_reply_to, references=references)

        logger.info("email_webhook_processed", sender=sender_email, subject=parsed_email.get("subject"))
        return {"status": "processed", "parsed": parsed_email, "agent_reply": agent_reply}

    except Exception as e:
        logger.error("email_webhook_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to process email")
