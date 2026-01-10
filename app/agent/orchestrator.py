"""LangGraph orchestrator for booking agent state machine"""

from typing import TypedDict, Annotated, Sequence, Literal
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
import structlog
from datetime import datetime

from app.services.llm_service import llm_service, LLMMessage
from app.services.supabase_client import supabase_client
from app.services.email_service import email_service
from app.agent.prompts import (
    BASE_SYSTEM_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    VENUE_INQUIRY_RESPONSE_PROMPT,
    AVAILABILITY_COLLECTION_PROMPT,
    NEGOTIATION_PROMPT,
    CONTRACT_GENERATION_PROMPT,
    FOLLOW_UP_PROMPT,
    CONFLICT_RESOLUTION_PROMPT,
    format_prompt,
    get_booking_constraints_text
)

logger = structlog.get_logger()


# Define the state structure
class AgentState(TypedDict):
    """State for the booking agent conversation"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    conversation_id: str
    sender_email: str
    sender_name: str
    sender_type: Literal["venue", "band_member", "admin"]
    intent: str
    booking_id: str | None
    booking_constraints: list[dict]
    requires_human_approval: bool
    next_action: str | None


class BookingAgent:
    """LangGraph-based booking agent orchestrator"""
    
    def __init__(self):
        """Initialize the booking agent"""
        self.graph = self._build_graph()
        logger.info("Initialized booking agent orchestrator")
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("classify_intent", self.classify_intent)
        workflow.add_node("handle_venue_inquiry", self.handle_venue_inquiry)
        workflow.add_node("handle_availability_request", self.handle_availability_request)
        workflow.add_node("handle_negotiation", self.handle_negotiation)
        workflow.add_node("handle_contract_request", self.handle_contract_request)
        workflow.add_node("check_approval_needed", self.check_approval_needed)
        workflow.add_node("save_to_database", self.save_to_database)
        
        # Set entry point
        workflow.set_entry_point("classify_intent")
        
        # Add conditional edges from intent classification
        workflow.add_conditional_edges(
            "classify_intent",
            self.route_by_intent,
            {
                "venue_inquiry": "handle_venue_inquiry",
                "availability_request": "handle_availability_request",
                "negotiation": "handle_negotiation",
                "contract_request": "handle_contract_request",
                "general": "handle_venue_inquiry",  # Default handler
            }
        )
        
        # All handlers go to approval check
        workflow.add_edge("handle_venue_inquiry", "check_approval_needed")
        workflow.add_edge("handle_availability_request", "check_approval_needed")
        workflow.add_edge("handle_negotiation", "check_approval_needed")
        workflow.add_edge("handle_contract_request", "check_approval_needed")
        
        # From approval check, save to database then end
        workflow.add_edge("check_approval_needed", "save_to_database")
        workflow.add_edge("save_to_database", END)
        
        return workflow.compile()
    
    async def classify_intent(self, state: AgentState) -> AgentState:
        """Classify the intent of the incoming message"""
        logger.info("Classifying intent", conversation_id=state["conversation_id"])
        
        # Get last user message
        user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        if not user_messages:
            state["intent"] = "general"
            return state
        
        last_message = user_messages[-1].content
        
        # Use LLM to classify intent
        context = {
            "message": last_message,
            "sender_type": state["sender_type"],
            "conversation_history": "\n".join([
                f"{m.__class__.__name__}: {m.content}" for m in state["messages"][-5:]
            ])
        }
        
        prompt = format_prompt(INTENT_CLASSIFICATION_PROMPT, context)
        
        messages = [
            LLMMessage(role="system", content=BASE_SYSTEM_PROMPT),
            LLMMessage(role="system", content=prompt),
            LLMMessage(role="user", content=last_message)
        ]
        
        response = await llm_service.generate(messages=messages, temperature=0.3, max_tokens=50)
        
        # Parse intent from response
        intent = response.content.lower().strip()
        if "venue" in intent or "booking" in intent:
            state["intent"] = "venue_inquiry"
        elif "availability" in intent or "available" in intent:
            state["intent"] = "availability_request"
        elif "negotiat" in intent or "price" in intent or "offer" in intent:
            state["intent"] = "negotiation"
        elif "contract" in intent:
            state["intent"] = "contract_request"
        else:
            state["intent"] = "general"

        # If sender is not a band member, force venue intent
        band_member_emails = [
            "dave@sickdaywithferris.band",
            "john@sickdaywithferris.band",
            "mike@sickdaywithferris.band",
            "sarah@sickdaywithferris.band"
        ]  # Add all band member emails here
        sender_email = (state.get("sender_email") or "").lower()
        # Only force venue_inquiry for the first message in a conversation
        is_first_message = len(state.get("messages", [])) <= 1
        if sender_email not in band_member_emails and is_first_message:
            state["intent"] = "venue_inquiry"
        
        logger.info("Intent classified", intent=state["intent"])
        return state
    
    def route_by_intent(self, state: AgentState) -> str:
        """Route to appropriate handler based on intent"""
        return state["intent"]
    
    async def handle_venue_inquiry(self, state: AgentState) -> AgentState:
        """Handle venue booking inquiries"""
        logger.info("Handling venue inquiry", conversation_id=state["conversation_id"])
        
        # Get booking constraints
        constraints = await supabase_client.get_booking_constraints()
        state["booking_constraints"] = constraints
        constraints_text = get_booking_constraints_text(constraints)

        # Get conversation history
        conversation_history = "\n".join([
            f"{m.__class__.__name__}: {m.content}" for m in state["messages"][-10:]
        ])

        # Use LLM to extract event details from the last user message
        last_user_message = state["messages"][-1].content if state["messages"] else ""
        extraction_prompt = (
            "Extract the following details from the message below. "
            "Return a JSON object with these keys: requested_dates, event_type, expected_attendance, payment_offer, pa_available, load_in_time. "
            "If a detail is not specified, use '(not specified)'.\n"
            "Examples:\n"
            "Message: 'We're planning a wedding on July 3, 2026 for 150 people. We'll need a 3-hour set, can pay $1200, and have a PA system. Load-in at 5pm.'\n"
            '{"requested_dates": "July 3, 2026", "event_type": "wedding", "expected_attendance": "150", "payment_offer": "$1200", "pa_available": "yes", "load_in_time": "5pm"}'\n"
            "Message: 'It's a backyard party for about 100 folks, no PA, budget is $1000, you can arrive 2 hours early.'\n"
            '{"requested_dates": "(not specified)", "event_type": "backyard party", "expected_attendance": "100", "payment_offer": "$1000", "pa_available": "no", "load_in_time": "2 hours early"}'\n"
            "Message: 'Corporate event, 200 people, July 10, need PA, $1500, load-in at 4pm.'\n"
            '{"requested_dates": "July 10", "event_type": "corporate event", "expected_attendance": "200", "payment_offer": "$1500", "pa_available": "yes", "load_in_time": "4pm"}'\n"
            "Message: 'I manage The Rusty Tap downtown and we’re looking to add live music on Friday nights this summer. Would you guys be interested in playing on June 12th from around 8–11pm? Crowd is usually 75–100 people.'\n"
            '{"requested_dates": "June 12th", "event_type": "bar gig", "expected_attendance": "75", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "(not specified)"}'\n"
            "Message: 'We’d love to have Sick Day with Ferris out sometime in late May or early June for an evening set. Typical shows are about 3 hours. Let me know if you’re available and what you charge.'\n"
            '{"requested_dates": "late May or early June", "event_type": "brewery gig", "expected_attendance": "(not specified)", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "(not specified)"}'\n"
            "Message: 'The City of Oak Ridge is planning its annual Independence Day celebration on July 4, 2026 at Central Park. Attendance is expected to be approximately 1,500–2,000 residents. We are seeking a band to perform from 7:00 PM to 9:30 PM prior to the fireworks display. Please let us know if your band is available and provide your booking requirements and fee.'\n"
            '{"requested_dates": "July 4, 2026", "event_type": "Independence Day celebration", "expected_attendance": "1500", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "(not specified)"}'\n"
            "Message: 'We’re interested in booking your band for two 90-minute sets in the afternoon and early evening. The event is outdoors and draws several thousand people. Sound and staging are provided.'\n"
            '{"requested_dates": "(not specified)", "event_type": "festival", "expected_attendance": "2000", "payment_offer": "(not specified)", "pa_available": "yes", "load_in_time": "(not specified)"}'\n"
            "Message: 'My fiancé and I are getting married on September 18, 2026, and we’re looking for a band for our reception. The venue is a private ranch just outside Austin. We’d love live music from about 6:30–10:00 pm. Guests will be around 120 people. Can you let us know if you’re available and what your pricing looks like?'\n"
            '{"requested_dates": "September 18, 2026", "event_type": "wedding reception", "expected_attendance": "120", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "(not specified)"}'\n"
            "Message: 'We’re planning a wedding in early November and need a band for the reception. Probably a few hours of music, mostly covers people can dance to. Event will be in San Marcos.'\n"
            '{"requested_dates": "early November", "event_type": "wedding reception", "expected_attendance": "(not specified)", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "(not specified)"}'\n"
            "Message: 'We’re hosting a company holiday party on December 12th at a hotel ballroom in Dallas. We’re expecting about 300 attendees and would like live music for approximately 2 hours starting around 8pm. Please send availability and a quote.'\n"
            '{"requested_dates": "December 12th", "event_type": "company holiday party", "expected_attendance": "300", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "8pm"}'\n"
            "Message: 'I’m throwing a big birthday party at my place on August 7th and wanted to see if you’re free. Probably 150ish people, mostly friends and family. Thinking a couple hours of music in the evening.'\n"
            '{"requested_dates": "August 7th", "event_type": "birthday party", "expected_attendance": "150", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "evening"}'\n"
            "Message: 'We’re organizing a charity fundraiser benefiting the local food bank on May 22nd. The event will be held at the Riverfront Pavilion and we expect around 400 attendees. We’re seeking a band to perform for roughly 3 hours in the evening. Please let us know your availability and whether you offer discounted rates for nonprofit events.'\n"
            '{"requested_dates": "May 22nd", "event_type": "charity fundraiser", "expected_attendance": "400", "payment_offer": "discounted rates", "pa_available": "(not specified)", "load_in_time": "evening"}'\n"
            "Message: 'We’re doing an event later this summer and need live music. Can you send info on pricing and availability?'\n"
            '{"requested_dates": "later this summer", "event_type": "event", "expected_attendance": "(not specified)", "payment_offer": "(not specified)", "pa_available": "(not specified)", "load_in_time": "(not specified)"}'\n"
            "Message: " + last_user_message
        )
        extraction_llm_messages = [
            LLMMessage(role="system", content="You are an expert information extractor for a band booking agent. Always return valid JSON. Do not explain, just output JSON."),
            LLMMessage(role="user", content=extraction_prompt)
        ]
        extraction_response = await llm_service.generate(messages=extraction_llm_messages, temperature=0.0, max_tokens=300)
        import json
        # Log raw LLM extraction output for debugging
        logger.info("llm_extraction_raw_output", raw=extraction_response.content)
        try:
            extracted = json.loads(extraction_response.content)
        except Exception:
            extracted = {}
        def normalize(val):
            if not val or val == "(not specified)":
                return "(not specified)"
            import re
            s = str(val).strip()
            # Normalize attendance (extract first number in range or phrase)
            if any(word in s.lower() for word in ["attendance", "people", "folks", "guests", "attendees", "crowd", "residents"]):
                m = re.search(r"(\d+)", s)
                return m.group(1) if m else s
            # Normalize payment (extract $ or number)
            if any(word in s.lower() for word in ["$", "budget", "pay", "fee", "quote", "pricing", "rate", "discount"]):
                m = re.search(r"\$?([\d,]+)", s.replace(",", ""))
                return f"${m.group(1)}" if m else s
            # Normalize PA
            if s.lower() in ["yes", "provided", "available", "have pa", "have a pa", "pa provided", "sound and staging are provided"]:
                return "yes"
            if s.lower() in ["no", "not available", "need pa", "no pa", "don't have pa", "do not have pa", "need you to bring one"]:
                return "no"
            # Normalize duration (e.g., "a couple hours", "3 hours", "two 90-minute sets")
            if any(word in s.lower() for word in ["hour", "set", "duration", "evening", "afternoon"]):
                m = re.search(r"(\d+\.?\d*)", s)
                return m.group(1) + " hours" if m else s
            # Normalize vague dates (e.g., "early November", "late May")
            if any(word in s.lower() for word in ["early", "late", "summer", "spring", "fall", "winter", "evening", "afternoon"]):
                return s
            return s
        requested_dates = normalize(extracted.get("requested_dates", "(not specified)"))
        event_type = normalize(extracted.get("event_type", "(not specified)"))
        expected_attendance = normalize(extracted.get("expected_attendance", "(not specified)"))
        payment_offer = normalize(extracted.get("payment_offer", "(not specified)"))
        pa_available = normalize(extracted.get("pa_available", "(not specified)"))
        load_in_time = normalize(extracted.get("load_in_time", "(not specified)"))

        context = {
            "venue_name": state.get("sender_name", "Venue"),
            "requested_dates": requested_dates,
            "band_availability_status": "pending",  # Could be improved with actual lookup
            "booking_constraints": constraints_text,
            "min_notice_days": 14,
            "conversation_history": conversation_history,
            "event_type": event_type,
            "expected_attendance": expected_attendance,
            "payment_offer": payment_offer,
            "pa_available": pa_available,
            "load_in_time": load_in_time
        }

        # Build a dynamic follow-up string for missing details
        missing_details = []
        if context["event_type"] == "(not specified)":
            missing_details.append("event type")
        if context["expected_attendance"] == "(not specified)":
            missing_details.append("expected attendance")
        if context["payment_offer"] == "(not specified)":
            missing_details.append("payment offer")
        if context["pa_available"] == "(not specified)":
            missing_details.append("PA system availability")
        if context["load_in_time"] == "(not specified)":
            missing_details.append("load-in time")

        if not missing_details:
            # All details present, transition to availability check
            # Save details to state for downstream handlers
            state["event_type"] = event_type
            state["expected_attendance"] = expected_attendance
            state["payment_offer"] = payment_offer
            state["pa_available"] = pa_available
            state["load_in_time"] = load_in_time
            state["requested_dates"] = requested_dates
            # Set intent to availability_request so orchestrator routes to next step
            state["intent"] = "availability_request"
            logger.info("venue_inquiry_complete_details", requested_dates=requested_dates, event_type=event_type, expected_attendance=expected_attendance, payment_offer=payment_offer, pa_available=pa_available, load_in_time=load_in_time)
            return state
        else:
            follow_up = "To proceed, could you please provide the following details: " + ", ".join(missing_details) + "."
            # Format prompt with context and follow-up
            prompt = format_prompt(VENUE_INQUIRY_RESPONSE_PROMPT, context) + ("\n" + follow_up if follow_up else "")
            # Convert LangChain messages to LLM service messages
            llm_messages = [LLMMessage(role="system", content=BASE_SYSTEM_PROMPT), LLMMessage(role="system", content=prompt)]
            for msg in state["messages"]:
                if isinstance(msg, HumanMessage):
                    llm_messages.append(LLMMessage(role="user", content=msg.content))
                elif isinstance(msg, AIMessage):
                    llm_messages.append(LLMMessage(role="assistant", content=msg.content))
            response = await llm_service.generate(messages=llm_messages, temperature=0.7, max_tokens=300)
            # Always patch agent signature in the final response
            patched_content = response.content.replace("[Your Name]", "Ferris").replace("[YourName]", "Ferris")
            # Add assistant response to messages
            state["messages"] = state["messages"] + [AIMessage(content=patched_content)]
            state["requires_human_approval"] = False
            # Log extracted details and patched content for debugging
            logger.info("venue_inquiry_response", requested_dates=requested_dates, event_type=event_type, expected_attendance=expected_attendance, payment_offer=payment_offer, pa_available=pa_available, load_in_time=load_in_time, patched_content=patched_content)
            return state
    
    async def handle_availability_request(self, state: AgentState) -> AgentState:
        """Handle availability collection from band members"""
        logger.info("Handling availability request", conversation_id=state["conversation_id"])
        
        # Ensure band_member_name is always filled (use email prefix if missing)
        sender_name = state.get("sender_name")
        if not sender_name or not sender_name.strip():
            sender_email = state.get("sender_email", "")
            band_member_name = sender_email.split("@")[0] if sender_email else "Band Member"
        else:
            band_member_name = sender_name.strip()
        context = {
            "band_member_name": band_member_name,
            "conversation_history": "\n".join([
                f"{m.__class__.__name__}: {m.content}" for m in state["messages"][-10:]
            ])
        }
        
        prompt = format_prompt(AVAILABILITY_COLLECTION_PROMPT, context)
        
        # Convert LangChain messages to LLM service messages
        llm_messages = [LLMMessage(role="system", content=BASE_SYSTEM_PROMPT), LLMMessage(role="system", content=prompt)]
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                llm_messages.append(LLMMessage(role="user", content=msg.content))
            elif isinstance(msg, AIMessage):
                llm_messages.append(LLMMessage(role="assistant", content=msg.content))
        
        response = await llm_service.generate(messages=llm_messages, temperature=0.7, max_tokens=250)
        
        state["messages"] = state["messages"] + [AIMessage(content=response.content)]
        state["requires_human_approval"] = False
        
        return state
    
    async def handle_negotiation(self, state: AgentState) -> AgentState:
        """Handle price negotiations and counteroffers"""
        logger.info("Handling negotiation", conversation_id=state["conversation_id"])
        
        # Get booking constraints
        constraints = await supabase_client.get_booking_constraints()
        state["booking_constraints"] = constraints
        constraints_text = get_booking_constraints_text(constraints)
        
        context = {
            "venue_name": state.get("sender_name", "Venue"),
            "booking_constraints": constraints_text,
            "conversation_history": "\n".join([
                f"{m.__class__.__name__}: {m.content}" for m in state["messages"][-10:]
            ])
        }
        
        prompt = format_prompt(NEGOTIATION_PROMPT, context)
        
        # Convert LangChain messages to LLM service messages
        llm_messages = [LLMMessage(role="system", content=BASE_SYSTEM_PROMPT), LLMMessage(role="system", content=prompt)]
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                llm_messages.append(LLMMessage(role="user", content=msg.content))
            elif isinstance(msg, AIMessage):
                llm_messages.append(LLMMessage(role="assistant", content=msg.content))
        
        response = await llm_service.generate(messages=llm_messages, temperature=0.7, max_tokens=300)
        
        state["messages"] = state["messages"] + [AIMessage(content=response.content)]
        
        # Check if terms are acceptable (requires human approval)
        if "accept" in response.content.lower() or "agree" in response.content.lower():
            state["requires_human_approval"] = True
            state["next_action"] = "pending_approval"
        else:
            state["requires_human_approval"] = False
        
        return state
    
    async def handle_contract_request(self, state: AgentState) -> AgentState:
        """Handle contract generation requests"""
        logger.info("Handling contract request", conversation_id=state["conversation_id"])
        
        context = {
            "venue_name": state.get("sender_name", "Venue"),
            "conversation_history": "\n".join([
                f"{m.__class__.__name__}: {m.content}" for m in state["messages"][-10:]
            ])
        }
        
        prompt = format_prompt(CONTRACT_GENERATION_PROMPT, context)
        
        # Convert LangChain messages to LLM service messages
        llm_messages = [LLMMessage(role="system", content=BASE_SYSTEM_PROMPT), LLMMessage(role="system", content=prompt)]
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                llm_messages.append(LLMMessage(role="user", content=msg.content))
            elif isinstance(msg, AIMessage):
                llm_messages.append(LLMMessage(role="assistant", content=msg.content))
        
        response = await llm_service.generate(messages=llm_messages, temperature=0.7, max_tokens=300)
        
        state["messages"] = state["messages"] + [AIMessage(content=response.content)]
        state["requires_human_approval"] = True  # Always require approval for contracts
        state["next_action"] = "contract_approval_needed"
        
        return state
    
    async def check_approval_needed(self, state: AgentState) -> AgentState:
        """Check if human approval is needed"""
        if state["requires_human_approval"]:
            logger.info(
                "Human approval required",
                conversation_id=state["conversation_id"],
                action=state.get("next_action")
            )
            # In production, this would trigger a notification to admins
            # For now, we just log it
        
        return state
    
    async def save_to_database(self, state: AgentState) -> AgentState:
        """Save conversation and messages to database"""
        logger.info("Saving to database", conversation_id=state["conversation_id"])
        
        try:
            # Save each new message to the database
            for message in state["messages"]:
                if isinstance(message, AIMessage):
                    # This is the agent's response
                    await supabase_client.create_message(
                        conversation_id=state["conversation_id"],
                        sender_type="agent",
                        sender_id="booking-agent",
                        sender_name="Booking Agent",
                        content=message.content,
                        role="assistant"
                    )
                elif isinstance(message, HumanMessage):
                    # This is the user's message
                    # Lookup or create contact for sender
                    contact = await supabase_client.get_contact_by_email(state["sender_email"])
                    if not contact:
                        contact_id = await supabase_client.create_contact(state["sender_email"], state["sender_name"] or "")
                    else:
                        contact_id = contact["id"]
                    # Ensure sender_name is always a safe string
                    if contact:
                        first_name = contact.get('first_name') or ''
                        last_name = contact.get('last_name') or ''
                        safe_sender_name = f"{first_name} {last_name}".strip() or (state["sender_email"].split("@", 1)[0] if state.get("sender_email") else "Unknown")
                    else:
                        safe_sender_name = state["sender_name"] or (state["sender_email"].split("@", 1)[0] if state.get("sender_email") else "Unknown")
                    await supabase_client.create_message(
                        conversation_id=state["conversation_id"],
                        sender_type=state["sender_type"],
                        sender_id=contact_id,
                        sender_name=safe_sender_name,
                        content=message.content,
                        role="user"
                    )
            
            logger.info("Saved messages to database", conversation_id=state["conversation_id"])
        
        except Exception as e:
            logger.error("Failed to save to database", error=str(e))
        
        return state
    
    async def process_message(
        self,
        message_content: str,
        sender_email: str,
        sender_name: str,
        sender_type: Literal["venue", "band_member", "admin"],
        conversation_id: str | None = None
    ) -> dict:
        """
        Process an incoming message through the agent
        
        Args:
            message_content: The message text
            sender_email: Sender's email address
            sender_name: Sender's name
            sender_type: Type of sender (venue, band_member, admin)
            conversation_id: Existing conversation ID (creates new if None)
        
        Returns:
            Dict with agent response and metadata
        """
        # Create or get conversation
        if not conversation_id:
            conversation = await supabase_client.create_conversation(
                channel="email",
                participants=[
                    {"email": sender_email, "name": sender_name, "type": sender_type},
                    {"email": "agent@sickdaywithferris.band", "name": "Booking Agent", "type": "agent"}
                ]
            )
            conversation_id = conversation["id"]
        
        # Initialize state
        initial_state: AgentState = {
            "messages": [HumanMessage(content=message_content)],
            "conversation_id": conversation_id,
            "sender_email": sender_email,
            "sender_name": sender_name,
            "sender_type": sender_type,
            "intent": "",
            "booking_id": None,
            "booking_constraints": [],
            "requires_human_approval": False,
            "next_action": None
        }
        
        # Run through the graph
        final_state = await self.graph.ainvoke(initial_state)
        
        # Get the agent's response (last assistant message)
        assistant_messages = [m for m in final_state["messages"] if isinstance(m, AIMessage)]
        agent_response = assistant_messages[-1].content if assistant_messages else ""
        
        return {
            "response": agent_response,
            "conversation_id": conversation_id,
            "intent": final_state["intent"],
            "requires_human_approval": final_state["requires_human_approval"],
            "next_action": final_state.get("next_action")
        }


# Global agent instance
booking_agent = BookingAgent()
