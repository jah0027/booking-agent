"""Booking endpoints"""

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date
import structlog

logger = structlog.get_logger()
router = APIRouter()


class BookingInquiry(BaseModel):
    """Booking inquiry from website form"""
    venue_name: str
    contact_email: EmailStr
    contact_name: str
    preferred_dates: Optional[List[str]] = None
    notes: Optional[str] = None


@router.post("/bookings/inquiry")
async def submit_booking_inquiry(inquiry: BookingInquiry):
    """
    Public booking inquiry form submission
    """
    logger.info(
        "booking_inquiry_received",
        venue_name=inquiry.venue_name,
        contact_email=inquiry.contact_email
    )
    
    # TODO: Create booking and conversation in database
    # TODO: Trigger agent to process inquiry
    
    return {
        "conversation_id": "temp-conv-id",
        "status": "received",
        "message": "Thank you for your inquiry! We'll be in touch soon."
    }
