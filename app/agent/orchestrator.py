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

        # Fetch band member emails from Supabase band_members table
        sender_email = (state.get("sender_email") or "").lower()
        is_first_message = len(state.get("messages", [])) <= 1
        try:
            band_members = await supabase_client.get_band_members()
            band_member_emails = [bm["email"].lower() for bm in band_members if bm.get("email")]
        except Exception as e:
            logger.error("Failed to fetch band member emails", error=str(e))
            band_member_emails = []
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


        # Use the full conversation history as the extraction target
        user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        conversation_text = "\n".join([m.content for m in user_messages])

        # Use or initialize event_details in state
        event_details = state.get("event_details") or {
            "requested_dates": "(not specified)",
            "event_type": "(not specified)",
            "expected_attendance": "(not specified)",
            "payment_offer": "(not specified)",
            "pa_available": "(not specified)",
            "load_in_time": "(not specified)"
        }

        # Build conversation_history string for context
        conversation_history = "\n".join([
            f"{m.__class__.__name__}: {m.content}" for m in state["messages"][-10:]
        ])

        # Improved extraction prompt for LLM
        extraction_prompt = (
            "Extract the following event details from the conversation below. "
            "Return only a valid JSON object with these keys: requested_dates, event_type, expected_attendance, payment_offer, pa_available, load_in_time. "
            "If a detail is not specified, use '(not specified)'. Do not explain. "
            "Dates may be in any format (e.g., 'July 3 2026', 'next Friday', '2026-07-03'). Scan the entire conversation for relevant details.\n\n"
            "Conversation: " + conversation_text + "\n\n"
            "Example JSON structure:\n"
            "{\n"
            "  \"requested_dates\": \"(not specified)\",\n"
            "  \"event_type\": \"(not specified)\",\n"
            "  \"expected_attendance\": \"(not specified)\",\n"
            "  \"payment_offer\": \"(not specified)\",\n"
            "  \"pa_available\": \"(not specified)\",\n"
            "  \"load_in_time\": \"(not specified)\"\n"
            "}\n"
        )
        extraction_llm_messages = [
            LLMMessage(role="system", content="You are an expert information extractor for a band booking agent. Always return valid JSON. Do not explain, just output JSON."),
            LLMMessage(role="user", content=extraction_prompt)
        ]
        extraction_response = await llm_service.generate(messages=extraction_llm_messages, temperature=0.0, max_tokens=300)
        import json
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
            s_lower = s.lower()
            if any(word in s_lower for word in ["attendance", "people", "folks", "guests", "attendees", "crowd", "residents"]):
                m = re.search(r"(\d+)", s)
                return m.group(1) if m else s
            m = re.search(r"about (\d+)", s_lower)
            if m:
                return m.group(1)
            if any(word in s_lower for word in ["$", "budget", "pay", "fee", "quote", "pricing", "rate", "discount"]):
                m = re.search(r"\$?([\d,]+)", s.replace(",", ""))
                return f"${m.group(1)}" if m else s
            m = re.search(r"(\d+) budg", s_lower)
            if m:
                return f"${m.group(1)}"
            if s_lower in ["yes", "provided", "available", "have pa", "have a pa", "pa provided", "sound and staging are provided"]:
                return "yes"
            if s_lower in ["no", "not available", "need pa", "no pa", "don't have pa", "do not have pa", "need you to bring one"]:
                return "no"
            if "bring one" in s_lower or "you will need to bring" in s_lower:
                return "no"
            if any(word in s_lower for word in ["hour", "set", "duration", "evening", "afternoon"]):
                m = re.search(r"(\d+\.?\d*)", s)
                return m.group(1) + " hours" if m else s
            if any(word in s_lower for word in ["early", "late", "summer", "spring", "fall", "winter", "evening", "afternoon"]):
                return s
            return s

        # Update event_details with normalized extracted values
        for key in event_details.keys():
            event_details[key] = normalize(extracted.get(key, event_details[key]))
        logger.info("llm_extraction_normalized", **event_details)
        state["event_details"] = event_details

        # Compose context for follow-up or next step
        context = {
            "venue_name": state.get("sender_name", "Venue"),
            "requested_dates": event_details["requested_dates"],
            "band_availability_status": "pending",
            "booking_constraints": constraints_text,
            "min_notice_days": 14,
            "conversation_history": conversation_history,
            "event_type": event_details["event_type"],
            "expected_attendance": event_details["expected_attendance"],
            "payment_offer": event_details["payment_offer"],
            "pa_available": event_details["pa_available"],
            "load_in_time": event_details["load_in_time"]
        }

        # Build a dynamic follow-up string for missing details
        missing_details = []
        if event_details["event_type"] == "(not specified)":
            missing_details.append("event type")
        if event_details["expected_attendance"] == "(not specified)":
            missing_details.append("expected attendance")
        if event_details["payment_offer"] == "(not specified)":
            missing_details.append("payment offer")
        if event_details["pa_available"] == "(not specified)":
            missing_details.append("PA system availability")
        if event_details["load_in_time"] == "(not specified)":
            missing_details.append("load-in time")

        if not missing_details:
            # All details present, transition to availability check
            state["event_type"] = event_details["event_type"]
            state["expected_attendance"] = event_details["expected_attendance"]
            state["payment_offer"] = event_details["payment_offer"]
            state["pa_available"] = event_details["pa_available"]
            state["load_in_time"] = event_details["load_in_time"]
            state["requested_dates"] = event_details["requested_dates"]
            state["intent"] = "availability_request"
            logger.info("venue_inquiry_complete_details", **event_details)
            return state
        else:
            follow_up = "To proceed, could you please provide the following details: " + ", ".join(missing_details) + "."
            prompt = format_prompt(VENUE_INQUIRY_RESPONSE_PROMPT, context) + ("\n" + follow_up if follow_up else "")
            llm_messages = [LLMMessage(role="system", content=BASE_SYSTEM_PROMPT), LLMMessage(role="system", content=prompt)]
            for msg in state["messages"]:
                if isinstance(msg, HumanMessage):
                    llm_messages.append(LLMMessage(role="user", content=msg.content))
                elif isinstance(msg, AIMessage):
                    llm_messages.append(LLMMessage(role="assistant", content=msg.content))
            response = await llm_service.generate(messages=llm_messages, temperature=0.7, max_tokens=300)
            patched_content = response.content.replace("[Your Name]", "Ferris").replace("[YourName]", "Ferris")
            state["messages"] = state["messages"] + [AIMessage(content=patched_content)]
            state["requires_human_approval"] = False
            logger.info("venue_inquiry_response", **event_details, patched_content=patched_content)
            return state
            # ...existing code...
    
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
