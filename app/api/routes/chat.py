"""Chat endpoints"""


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
import structlog
import dateparser
from datetime import datetime, timedelta
from app.services.supabase_client import SupabaseClient
from app.services.llm_service import LLMService, LLMMessage

logger = structlog.get_logger()
router = APIRouter()


class ChatRequest(BaseModel):
    """Chat message request"""
    message: str
    sender_email: EmailStr
    sender_name: str
    band_member_id: str = None
    is_admin: bool = False  # New flag to distinguish admin vs public


class ChatResponse(BaseModel):
    """Chat message response"""
    conversation_id: str
    response: str



@router.post("/chat", response_model=ChatResponse)
async def start_chat(request: ChatRequest):
    """
    Start a new conversation (venue or band member inquiry)
    """
    logger.info(
        "chat_started",
        sender_email=request.sender_email,
        sender_name=request.sender_name
    )


    # 1. Try LLM extraction for date(s)
    llm = LLMService()
    # New: Ask LLM for intent (block or check)
    if request.is_admin:
        intent_system = "You are a helpful assistant that classifies user intent for band availability."
        date_system = "You are a helpful assistant that extracts unavailable dates from user messages."
    else:
        intent_system = (
            "You are a polite, professional band manager for SickDay. "
            "You always refer to the band as 'the band' or 'SickDay' unless a specific member is mentioned. "
            "Classify the user's message: does it ask to block out a date (mark unavailable) or to check if a date is available? "
            "Reply with 'BLOCK' for block out, 'CHECK' for availability check, or 'NONE' if neither."
        )
        date_system = (
            "You are a polite, professional band manager for SickDay. "
            "You always refer to the band as 'the band' or 'SickDay' unless a specific member is mentioned. "
            "Extract the unavailable date or date range from this message as ISO 8601 (YYYY-MM-DD or YYYY-MM-DD to YYYY-MM-DD). "
            "Dates may be written in word or number format (e.g., 'July 4th', 'the 4th of July', '7/4', 'July fourth', etc.), and there may be misspellings or informal phrasing. "
            f"Be robust to typos and natural language. If the year is not specified, always return the next future occurrence of that date (relative to today: {datetime.now().strftime('%Y-%m-%d')}). "
            "If no date is found, reply with 'NONE'."
        )
    intent_prompt = (
        "Does this message ask to block out a date (mark unavailable) or to check if a date is available? "
        "Reply with 'BLOCK' for block out, 'CHECK' for availability check, or 'NONE' if neither. Message: '" + request.message + "'"
    )
    intent_response = await llm.generate([
        LLMMessage(role="system", content=intent_system),
        LLMMessage(role="user", content=intent_prompt)
    ], model=None, temperature=0)
    intent = intent_response.content.strip().upper()
    logger.info("llm_extracted_intent", intent=intent, original_message=request.message)

    prompt = (
        "Extract the unavailable date or date range from this message as ISO 8601 (YYYY-MM-DD or YYYY-MM-DD to YYYY-MM-DD). "
        "Dates may be written in word or number format (e.g., 'July 4th', 'the 4th of July', '7/4', 'July fourth', etc.), and there may be misspellings or informal phrasing. "
        f"Be robust to typos and natural language. If the year is not specified, always return the next future occurrence of that date (relative to today: {datetime.now().strftime('%Y-%m-%d')}). "
        "If no date is found, reply with 'NONE'. Message: '" + request.message + "'"
    )
    llm_response = await llm.generate([
        LLMMessage(role="system", content=date_system),
        LLMMessage(role="user", content=prompt)
    ], model=None, temperature=0)
    date_text = llm_response.content.strip()
    logger.info("llm_extracted_date_text", date_text=date_text, original_message=request.message)

    import re
    parsed_date = None
    date_range_start = None
    date_range_end = None
    today = datetime.now()
    def next_occurrence(month: int, day: int):
        year = today.year
        try:
            candidate = datetime(year, month, day)
        except ValueError:
            return None
        if candidate < today:
            candidate = datetime(year + 1, month, day)
        return candidate

    def parse_with_next_year_fallback(date_str):
        # Use regex to check if year is present in the original string
        year_in_str = re.search(r'\b\d{4}\b', date_str)
        parsed = dateparser.parse(date_str)
        if parsed and not year_in_str:
            # Always use next occurrence logic for month/day with no year
            month = parsed.month
            day = parsed.day
            candidate = datetime(today.year, month, day)
            if candidate < today:
                candidate = datetime(today.year + 1, month, day)
            return candidate
        return parsed

    if date_text and date_text != 'NONE':
        logger.info("parsing_date_range", date_text=date_text)
        if 'to' in date_text:
            parts = [p.strip() for p in date_text.split('to')]
            if len(parts) == 2:
                date_range_start = parse_with_next_year_fallback(parts[0])
                date_range_end = parse_with_next_year_fallback(parts[1])
        else:
            date_range_start = parse_with_next_year_fallback(date_text)
            date_range_end = date_range_start

    # 2. Fallback to dateparser if LLM fails
    if not date_range_start:
        logger.info("date_range_start_not_found", fallback_message=request.message)
        date_range_start = parse_with_next_year_fallback(request.message)
        date_range_end = date_range_start


    # If intent is CHECK and no date is found, prompt for a date
    if not date_range_start:
        if intent == 'CHECK':
            return ChatResponse(
                conversation_id="temp-conv-id",
                response="Please specify a date to check availability (e.g., 'Is John available July 4th?')."
            )
        else:
            return ChatResponse(
                conversation_id="temp-conv-id",
                response="Sorry, I could not process that."
            )

    # If intent is CHECK, query DB for availability
    if intent == 'CHECK':
        logger.info("intent_is_check", intent=intent, date_range_start=str(date_range_start), date_range_end=str(date_range_end))
        # Get all band members for context (including email)
        supabase = SupabaseClient()
        client = supabase.get_client()
        result = client.table("band_members").select("id,name,email").execute()
        band_members = result.data if result.data else []
        band_member_names = ', '.join([m['name'] for m in band_members])
        llm = LLMService()
        name_prompt = (
            f"Band members: {band_member_names}. "
            "If the message refers to all band members (e.g., 'the whole band', 'everyone', 'all members'), reply with 'ALL'. "
            "If the message refers to a band member by name (even partial, nickname, or misspelled), extract the closest full name from the list above. "
            "Always return the exact full name from the list, even if the user only provides a first name, nickname, or a misspelling. "
            "If no name is found, reply with 'NONE'. Message: '" + request.message + "'"
        )
        name_response = await llm.generate([
            LLMMessage(role="system", content="You are a helpful assistant that extracts names from user messages, using the provided band member list for matching."),
            LLMMessage(role="user", content=name_prompt)
        ], model=None, temperature=0)
        extracted_name = name_response.content.strip()
        logger.info("llm_extracted_name", extracted_name=extracted_name, band_member_names=band_member_names, original_message=request.message)
        logger.info(
            "llm_extracted_name",
            extracted_name=extracted_name,
            band_member_names=band_member_names,
            original_message=request.message
        )
        # If no name is found (NONE), treat as ALL for availability check
        if extracted_name == 'ALL' or extracted_name == 'NONE':
            # Check for all band members
            unavailable = []
            for member in band_members:
                avail = client.table("availability").select("id").eq("band_member_id", member["id"]).eq("date_range_start", date_range_start.date()).eq("status", "unavailable").execute()
                if avail.data:
                    unavailable.append(member["name"])
            if request.is_admin:
                # Admin: show unavailable members
                if unavailable:
                    response_text = f"Not available: {', '.join(unavailable)} on {date_range_start.strftime('%B %d, %Y')}."
                else:
                    response_text = f"The whole band is available on {date_range_start.strftime('%B %d, %Y')}."
            else:
                # Public: only show band-level status
                if unavailable:
                    response_text = f"SickDay is not available on {date_range_start.strftime('%B %d, %Y')}."
                else:
                    response_text = f"SickDay is available on {date_range_start.strftime('%B %d, %Y')}."
            logger.info("chat_response", response=response_text)
            return ChatResponse(
                conversation_id="temp-conv-id",
                response=response_text
            )
        else:
            # Check for a specific member
            found = None
            for member in band_members:
                if member["name"].strip().lower() == extracted_name.strip().lower():
                    found = member
                    break
            if not found:
                # Try partial/fuzzy match
                import difflib
                extracted_lower = extracted_name.strip().lower()
                for member in band_members:
                    if extracted_lower in member["name"].strip().lower():
                        found = member
                        break
                if not found:
                    names = [m["name"] for m in band_members]
                    matches = difflib.get_close_matches(extracted_name, names, n=1, cutoff=0.6)
                    if matches:
                        for member in band_members:
                            if member["name"] == matches[0]:
                                found = member
                                break
            if found:
                # Send an email to the band member about availability
                from fastapi import Request
                import httpx
                # Compose the freeform message for the email
                email_message = f"Hi {found['name']}, could you please confirm your availability for {date_range_start.strftime('%B %d, %Y')}?"\
                    f"\n\nOriginal request: {request.message}"
                # Call the email endpoint internally (or you could call the service directly)
                try:
                    async with httpx.AsyncClient() as client_http:
                        email_payload = {
                            "band_member_email": found["email"],
                            "band_member_name": found["name"],
                            "message": email_message
                        }
                        # Assumes the API is running locally; adjust if needed
                        email_response = await client_http.post("http://localhost:8000/api/v1/agent/send-bandmember-email", json=email_payload)
                        if email_response.status_code == 200:
                            response_text = f"{found['name']} is being contacted for their availability on {date_range_start.strftime('%B %d, %Y')}. An email has been sent."
                        else:
                            response_text = f"Tried to contact {found['name']} by email, but there was an error."
                except Exception as e:
                    logger.error("bandmember_email_send_failed", error=str(e))
                    response_text = f"Error sending email to {found['name']}."
                logger.info("chat_response", response=response_text)
                return ChatResponse(
                    conversation_id="temp-conv-id",
                    response=response_text
                )
            else:
                response_text = f"Sorry, I couldn't find a band member named '{extracted_name}'. Band members: {band_member_names}. Please specify the full name."
                logger.info("chat_response", response=response_text)
                return ChatResponse(
                    conversation_id="temp-conv-id",
                    response=response_text
                )

    # Get all band members for context
    supabase = SupabaseClient()
    client = supabase.get_client()
    result = client.table("band_members").select("id,name").execute()
    band_members = result.data if result.data else []
    band_member_names = ', '.join([m['name'] for m in band_members])
    llm = LLMService()
    name_prompt = (
        f"Band members: {band_member_names}. "
        "If the message refers to all band members (e.g., 'the whole band', 'everyone', 'all members'), reply with 'ALL'. "
        "If the message refers to a band member by name (even partial, nickname, or misspelled), extract the closest full name from the list above. "
        "Always return the exact full name from the list, even if the user only provides a first name, nickname, or a misspelling. "
        "If no name is found, reply with 'NONE'. Message: '" + request.message + "'"
    )
    name_response = await llm.generate([
        LLMMessage(role="system", content="You are a helpful assistant that extracts names from user messages, using the provided band member list for matching."),
        LLMMessage(role="user", content=name_prompt)
    ], model=None, temperature=0)
    extracted_name = name_response.content.strip()
    logger.info(
        "llm_extracted_name",
        extracted_name=extracted_name,
        band_member_names=band_member_names,
        original_message=request.message
    )

    band_member_id = request.band_member_id
    if extracted_name == 'ALL':
        # Block out for all band members
        supabase = SupabaseClient()
        failed = []
        for member in band_members:
            try:
                await supabase.create_availability(
                    band_member_id=member["id"],
                    date_range_start=date_range_start,
                    date_range_end=date_range_end,
                    status="unavailable"
                )
            except Exception as e:
                failed.append(member["name"])
        if date_range_start == date_range_end:
            date_str = date_range_start.strftime('%B %d, %Y')
        else:
            date_str = f"{date_range_start.strftime('%B %d, %Y')} to {date_range_end.strftime('%B %d, %Y')}"
        if not failed:
            response_text = f"Blocked out {date_str} as unavailable for all band members."
        else:
            response_text = f"Blocked out {date_str} for all except: {', '.join(failed)}."
        logger.info("chat_response", response=response_text)
        return ChatResponse(
            conversation_id="temp-conv-id",
            response=response_text
        )
    if extracted_name and extracted_name != 'NONE':
        # Try exact match first (case-insensitive)
        found = None
        for member in band_members:
            if member["name"].strip().lower() == extracted_name.strip().lower():
                found = member
                break
        # If not found, try partial/fuzzy match
        if not found:
            import difflib
            # Try partial match (first name, substring)
            extracted_lower = extracted_name.strip().lower()
            for member in band_members:
                if extracted_lower in member["name"].strip().lower():
                    found = member
                    break
        if not found:
            # Try fuzzy match using difflib
            names = [m["name"] for m in band_members]
            matches = difflib.get_close_matches(extracted_name, names, n=1, cutoff=0.6)
            if matches:
                for member in band_members:
                    if member["name"] == matches[0]:
                        found = member
                        break
        if found:
            band_member_id = found["id"]
        else:
            # No match, show all band members and ask user to clarify
            response_text = f"Sorry, I couldn't find a band member named '{extracted_name}'. Band members: {band_member_names}. Please specify the full name."
            logger.info("chat_response", response=response_text)
            return ChatResponse(
                conversation_id="temp-conv-id",
                response=response_text
            )
    if not band_member_id or band_member_id == "demo-band-member-id":
        # Always require a valid band_member_id, never use the placeholder
        response_text = f"Sorry, I couldn't determine which band member you meant. Band members: {band_member_names}. Please specify the full name."
        logger.info("chat_response", response=response_text)
        return ChatResponse(
            conversation_id="temp-conv-id",
            response=response_text
        )
    supabase = SupabaseClient()
    try:
        await supabase.create_availability(
            band_member_id=band_member_id,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            status="unavailable"
        )
        if date_range_start == date_range_end:
            date_str = date_range_start.strftime('%B %d, %Y')
        else:
            date_str = f"{date_range_start.strftime('%B %d, %Y')} to {date_range_end.strftime('%B %d, %Y')}"
        response_text = f"Blocked out {date_str} as unavailable."
        logger.info("chat_response", response=response_text)
        return ChatResponse(
            conversation_id="temp-conv-id",
            response=response_text
        )
    except Exception as e:
        logger.error("availability_save_failed", error=str(e))
        response_text = "Sorry, there was an error saving your unavailable date."
        logger.info("chat_response", response=response_text)
        return ChatResponse(
            conversation_id="temp-conv-id",
            response=response_text
        )


@router.post("/chat/{conversation_id}/message", response_model=ChatResponse)
async def continue_chat(conversation_id: str, request: ChatRequest):
    """
    Continue an existing conversation (public or admin)
    """
    logger.info(
        "chat_message",
        conversation_id=conversation_id,
        sender_email=request.sender_email
    )
    # TODO: Retrieve conversation context from database (not yet implemented)
    # For now, echo the message and simulate context-aware response
    response_text = f"[Simulated] Continuing conversation {conversation_id} as {'admin' if request.is_admin else 'public'}: {request.message}"
    return ChatResponse(
        conversation_id=conversation_id,
        response=response_text
    )
