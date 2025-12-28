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
        
        context = {
            "venue_name": state.get("sender_name", "Venue"),
            "booking_constraints": constraints_text,
            "conversation_history": conversation_history
        }
        
        prompt = format_prompt(VENUE_INQUIRY_RESPONSE_PROMPT, context)
        
        # Convert LangChain messages to LLM service messages
        llm_messages = [LLMMessage(role="system", content=BASE_SYSTEM_PROMPT), LLMMessage(role="system", content=prompt)]
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                llm_messages.append(LLMMessage(role="user", content=msg.content))
            elif isinstance(msg, AIMessage):
                llm_messages.append(LLMMessage(role="assistant", content=msg.content))
        
        response = await llm_service.generate(messages=llm_messages, temperature=0.7, max_tokens=300)
        
        # Add assistant response to messages
        state["messages"] = state["messages"] + [AIMessage(content=response.content)]
        state["requires_human_approval"] = False
        
        return state
    
    async def handle_availability_request(self, state: AgentState) -> AgentState:
        """Handle availability collection from band members"""
        logger.info("Handling availability request", conversation_id=state["conversation_id"])
        
        context = {
            "band_member_name": state.get("sender_name", "Band Member"),
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
                    await supabase_client.create_message(
                        conversation_id=state["conversation_id"],
                        sender_type=state["sender_type"],
                        sender_id=state["sender_email"],
                        sender_name=state["sender_name"],
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
