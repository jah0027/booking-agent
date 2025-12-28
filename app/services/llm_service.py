"""LLM Service for AI agent interactions"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Union
from enum import Enum

import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import settings

logger = structlog.get_logger()


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    GEMINI = "gemini"


class LLMMessage(BaseModel):
    """Standardized message format"""
    role: str = Field(..., description="Message role: system, user, or assistant")
    content: str = Field(..., description="Message content")
    
    
class LLMResponse(BaseModel):
    """Standardized LLM response"""
    content: str = Field(..., description="Generated text content")
    model: str = Field(..., description="Model used for generation")
    provider: LLMProvider = Field(..., description="Provider used")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage stats")
    finish_reason: Optional[str] = Field(None, description="Completion finish reason")


class LLMError(Exception):
    """Base exception for LLM service errors"""
    pass


class LLMService:
    """
    Unified interface for LLM interactions.
    Supports OpenAI (GPT-4) with automatic retries and error handling.
    Gemini support can be added later if needed.
    """
    
    def __init__(self):
        self.openai_client: Optional[AsyncOpenAI] = None
        
        # Initialize OpenAI client if API key is available
        if settings.openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            logger.info("Initialized OpenAI client")
        else:
            logger.warning("No LLM provider configured - OpenAI API key missing")
    
    def _get_provider_from_model(self, model: str) -> LLMProvider:
        """Determine provider from model name"""
        if model.startswith("gpt-") or model.startswith("o1-"):
            return LLMProvider.OPENAI
        elif model.startswith("gemini-"):
            return LLMProvider.GEMINI
        else:
            # Default to OpenAI
            return LLMProvider.OPENAI
    
    async def generate(
        self,
        messages: List[Union[LLMMessage, Dict[str, str]]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.
        
        Args:
            messages: List of messages in the conversation
            model: Model to use (defaults to settings.llm_model)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            response_format: Optional response format (e.g., {"type": "json_object"})
            max_retries: Number of retry attempts on failure
            
        Returns:
            LLMResponse with generated content and metadata
            
        Raises:
            LLMError: If generation fails after all retries
        """
        model = model or settings.llm_model
        provider = self._get_provider_from_model(model)
        
        # Convert messages to proper format
        formatted_messages = [
            msg if isinstance(msg, dict) else msg.model_dump()
            for msg in messages
        ]
        
        logger.info(
            "Generating LLM response",
            provider=provider.value,
            model=model,
            message_count=len(formatted_messages),
            temperature=temperature,
        )
        
        for attempt in range(max_retries):
            try:
                if provider == LLMProvider.OPENAI:
                    return await self._generate_openai(
                        messages=formatted_messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                    )
                else:
                    raise LLMError(f"Unsupported provider: {provider}. Only OpenAI is currently configured.")
                    
            except Exception as e:
                logger.warning(
                    "LLM generation attempt failed",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                    provider=provider.value,
                )
                
                if attempt == max_retries - 1:
                    raise LLMError(f"LLM generation failed after {max_retries} attempts: {str(e)}")
                
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
        
        raise LLMError("Unexpected error in LLM generation")
    
    async def _generate_openai(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[Dict[str, Any]],
    ) -> LLMResponse:
        """Generate completion using OpenAI API"""
        if not self.openai_client:
            raise LLMError("OpenAI client not initialized - missing API key")
        
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
            
        if response_format:
            kwargs["response_format"] = response_format
        
        response = await self.openai_client.chat.completions.create(**kwargs)
        
        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            provider=LLMProvider.OPENAI,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            finish_reason=response.choices[0].finish_reason,
        )
    
    async def generate_json(
        self,
        messages: List[Union[LLMMessage, Dict[str, str]]],
        response_model: type[BaseModel],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> BaseModel:
        """
        Generate structured JSON output that conforms to a Pydantic model.
        
        Args:
            messages: List of messages in the conversation
            response_model: Pydantic model to validate response against
            model: Model to use (defaults to settings.llm_model)
            temperature: Sampling temperature (0-1)
            max_retries: Number of retry attempts on failure
            
        Returns:
            Instance of response_model with parsed data
            
        Raises:
            LLMError: If generation or parsing fails
        """
        # Add instruction for JSON output
        last_message = messages[-1]
        if isinstance(last_message, dict):
            last_message["content"] += f"\n\nRespond with valid JSON matching this schema:\n{response_model.model_json_schema()}"
        else:
            last_message.content += f"\n\nRespond with valid JSON matching this schema:\n{response_model.model_json_schema()}"
        
        # Request JSON format from OpenAI
        response_format = {"type": "json_object"} if model and model.startswith("gpt-") else None
        
        response = await self.generate(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format=response_format,
            max_retries=max_retries,
        )
        
        # Parse and validate JSON
        try:
            data = json.loads(response.content)
            return response_model.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse LLM JSON response", error=str(e), content=response.content)
            raise LLMError(f"Failed to parse JSON response: {str(e)}")
    
    async def classify_intent(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Classify the intent of a user message.
        
        Returns one of: initial_inquiry, availability_response, negotiation, 
        confirmation, contract_acceptance, follow_up, other
        """
        system_prompt = """You are an intent classifier for a band booking agent.
Classify the user's message into one of these intents:
- initial_inquiry: User is making a new booking inquiry
- availability_response: Band member responding about their availability
- negotiation: Discussing dates, times, payment, or other booking details
- confirmation: User confirming or accepting a proposed booking
- contract_acceptance: User accepting the contract terms
- follow_up: Following up on a previous conversation
- other: Message doesn't fit other categories

Respond with just the intent name, nothing else."""

        messages = [
            LLMMessage(role="system", content=system_prompt),
        ]
        
        if conversation_history:
            messages.extend([LLMMessage(**msg) for msg in conversation_history])
            
        messages.append(LLMMessage(role="user", content=f"Classify this message:\n\n{message}"))
        
        response = await self.generate(
            messages=messages,
            temperature=0.3,  # Lower temperature for classification
            max_tokens=50,
        )
        
        return response.content.strip().lower()


# Global LLM service instance
llm_service = LLMService()
