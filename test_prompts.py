"""Test system prompts with real LLM"""

import asyncio
from datetime import date
from app.agent.prompts import (
    BASE_SYSTEM_PROMPT,
    VENUE_INQUIRY_RESPONSE_PROMPT,
    NEGOTIATION_PROMPT,
    format_prompt,
    get_booking_constraints_text
)
from app.services.llm_service import llm_service, LLMMessage


async def test_venue_inquiry_response():
    """Test responding to a venue inquiry"""
    print("="*60)
    print("TEST 1: Venue Inquiry Response")
    print("="*60)
    
    # Simulate booking constraints
    constraints = [
        {"constraint_type": "min_payment", "value": {"amount": 300, "currency": "USD"}},
        {"constraint_type": "min_notice_days", "value": {"days": 14}}
    ]
    
    context = {
        "venue_name": "The Blue Room",
        "requested_dates": "March 15, 2025",
        "band_availability_status": "Checking with band members",
        "booking_constraints": get_booking_constraints_text(constraints),
        "min_payment": 300,
        "min_notice_days": 14
    }
    
    prompt = format_prompt(VENUE_INQUIRY_RESPONSE_PROMPT, context)
    
    messages = [
        LLMMessage(role="system", content=BASE_SYSTEM_PROMPT),
        LLMMessage(role="system", content=prompt),
        LLMMessage(
            role="user",
            content="Hi, I'm interested in booking Sick Day with Ferris for a show at The Blue Room on March 15th. Are you guys available?"
        )
    ]
    
    response = await llm_service.generate(messages=messages, temperature=0.7, max_tokens=300)
    
    print(f"\nVenue Inquiry:")
    print("Hi, I'm interested in booking Sick Day with Ferris for a show at The Blue Room on March 15th. Are you guys available?")
    print(f"\nAgent Response:")
    print(response.content)
    print(f"\nTokens used: {response.usage}")


async def test_negotiation():
    """Test negotiating with a venue"""
    print("\n" + "="*60)
    print("TEST 2: Negotiation (Low Payment Offer)")
    print("="*60)
    
    constraints = [
        {"constraint_type": "min_payment", "value": {"amount": 300, "currency": "USD"}},
    ]
    
    context = {
        "venue_name": "Joe's Bar",
        "proposed_dates": "April 20, 2025",
        "venue_offer": "$150 for 2-hour set",
        "band_availability": "All members available",
        "booking_constraints": get_booking_constraints_text(constraints),
        "min_payment": 300,
        "min_notice_days": 14,
        "max_shows_per_month": 8,
        "conversation_history": "Initial inquiry received 2 days ago"
    }
    
    prompt = format_prompt(NEGOTIATION_PROMPT, context)
    
    messages = [
        LLMMessage(role="system", content=BASE_SYSTEM_PROMPT),
        LLMMessage(role="system", content=prompt),
        LLMMessage(
            role="user",
            content="Great to hear you're interested! We can offer $150 for a 2-hour set on April 20th. Does that work?"
        )
    ]
    
    response = await llm_service.generate(messages=messages, temperature=0.7, max_tokens=300)
    
    print(f"\nVenue Offer:")
    print("Great to hear you're interested! We can offer $150 for a 2-hour set on April 20th. Does that work?")
    print(f"\nAgent Response:")
    print(response.content)
    print(f"\nTokens used: {response.usage}")


async def test_acceptable_offer():
    """Test accepting a good offer (with human approval caveat)"""
    print("\n" + "="*60)
    print("TEST 3: Negotiation (Acceptable Offer)")
    print("="*60)
    
    constraints = [
        {"constraint_type": "min_payment", "value": {"amount": 300, "currency": "USD"}},
    ]
    
    context = {
        "venue_name": "The Roxy Theatre",
        "proposed_dates": "May 10, 2025",
        "venue_offer": "$500 for 3-hour set, PA provided",
        "band_availability": "All members confirmed available",
        "booking_constraints": get_booking_constraints_text(constraints),
        "min_payment": 300,
        "min_notice_days": 14,
        "max_shows_per_month": 8,
        "conversation_history": "Discussed dates yesterday, band confirmed availability"
    }
    
    prompt = format_prompt(NEGOTIATION_PROMPT, context)
    
    messages = [
        LLMMessage(role="system", content=BASE_SYSTEM_PROMPT),
        LLMMessage(role="system", content=prompt),
        LLMMessage(
            role="user",
            content="We'd love to have you guys! We can offer $500 for a 3-hour set on May 10th. We have a full PA system and sound engineer. Sound good?"
        )
    ]
    
    response = await llm_service.generate(messages=messages, temperature=0.7, max_tokens=300)
    
    print(f"\nVenue Offer:")
    print("We'd love to have you guys! We can offer $500 for a 3-hour set on May 10th. We have a full PA system and sound engineer. Sound good?")
    print(f"\nAgent Response:")
    print(response.content)
    print(f"\nTokens used: {response.usage}")
    
    # Check if response mentions human approval
    if "approval" in response.content.lower() or "present" in response.content.lower():
        print("\n✅ GOOD: Agent correctly mentioned needing approval/presenting to band")
    else:
        print("\n⚠️  WARNING: Agent might have forgotten to mention human approval requirement")


async def main():
    """Run all prompt tests"""
    try:
        print("\n🧪 Testing System Prompts with GPT-4\n")
        
        await test_venue_inquiry_response()
        await test_negotiation()
        await test_acceptable_offer()
        
        print("\n" + "="*60)
        print("✅ All prompt tests completed!")
        print("\nAnalysis:")
        print("- Check that responses are professional and on-brand")
        print("- Verify agent respects constraints (min payment, approval needed)")
        print("- Ensure agent doesn't make unauthorized commitments")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
