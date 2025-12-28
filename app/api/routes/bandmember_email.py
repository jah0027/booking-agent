from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.services.email_service import EmailService
from app.services.llm_service import LLMService, LLMMessage
import structlog

router = APIRouter()
logger = structlog.get_logger()

class BandMemberEmailRequest(BaseModel):
    band_member_email: EmailStr
    band_member_name: str
    message: str  # Freeform message or instruction
    conversation_id: str = None  # Optional, for threading
    booking_id: str = None  # Optional, for context

class BandMemberEmailResponse(BaseModel):
    status: str
    email_id: str = None
    sent_at: str = None
    error: str = None

@router.post("/send-bandmember-email", response_model=BandMemberEmailResponse)
async def send_bandmember_email(request: BandMemberEmailRequest):
    """
    Trigger the agent to send a crafted availability email to a band member using LLM.
    """
    llm = LLMService()
    # Prompt the LLM to write a professional, friendly availability request
    prompt = (
        f"You are a booking agent for a band. Write a short, friendly email to the band member named {request.band_member_name} "
        f"asking them to confirm their availability. Include the following context or instructions: '{request.message}'. "
        "Be clear, polite, and concise. Do not include any sensitive information."
    )
    llm_response = await llm.generate([
        LLMMessage(role="system", content="You are a helpful booking agent."),
        LLMMessage(role="user", content=prompt)
    ], model=None, temperature=0.7)
    message_content = llm_response.content.strip()

    email_service = EmailService()
    try:
        result = await email_service.send_availability_request(
            band_member_email=request.band_member_email,
            band_member_name=request.band_member_name,
            message_content=message_content,
            conversation_id=request.conversation_id or "bandmember-avail-check",
            booking_id=request.booking_id
        )
        logger.info("bandmember_email_sent", to=request.band_member_email, email_id=result.get("email_id"))
        return BandMemberEmailResponse(status="sent", email_id=result.get("email_id"), sent_at=result.get("sent_at"))
    except Exception as e:
        logger.error("bandmember_email_failed", error=str(e))
        return BandMemberEmailResponse(status="error", error=str(e))
