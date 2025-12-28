"""FastAPI server to connect the website chat to the booking agent"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import structlog

from app.agent.orchestrator import booking_agent

load_dotenv()

logger = structlog.get_logger()

app = FastAPI(title="Booking Agent API", version="1.0.0")

# Allow requests from your website
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3002",  # Your current dev server
        "http://localhost:5173",  # Vite default
        "http://localhost:3000",  # Alternative
        "https://sickdaywithferris.band",  # Production
        "https://www.sickdaywithferris.band",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    sender_name: str
    sender_email: str
    sender_type: str = "venue"
    venue_name: str | None = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    intent: str
    requires_human_approval: bool
    next_action: str | None


@app.get("/")
async def root():
    return {"message": "Sick Day with Ferris Booking Agent API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a chat message from the website booking widget
    
    Args:
        request: Chat message with sender information
    
    Returns:
        Agent's response with metadata
    """
    try:
        logger.info(
            "Processing chat message",
            sender_name=request.sender_name,
            sender_email=request.sender_email,
            has_conversation_id=bool(request.conversation_id)
        )
        
        result = await booking_agent.process_message(
            message_content=request.message,
            sender_email=request.sender_email,
            sender_name=request.sender_name,
            sender_type=request.sender_type,
            conversation_id=request.conversation_id
        )
        
        logger.info(
            "Chat processed successfully",
            conversation_id=result["conversation_id"],
            intent=result["intent"]
        )
        
        return ChatResponse(**result)
    
    except Exception as e:
        logger.error("Chat processing failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Booking Agent API server")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
