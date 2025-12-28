"""Test updated pricing prompts"""

import asyncio
from app.agent.prompts import (
    BASE_SYSTEM_PROMPT,
    NEGOTIATION_PROMPT,
    format_prompt,
    get_booking_constraints_text
)
from app.services.llm_service import llm_service, LLMMessage


async def test_updated_pricing():
    """Test negotiation with updated rates"""
    print("="*60)
    print("TEST: Negotiation with Updated $1,500 Rate")
    print("="*60)
    
    # Simulate updated booking constraints
    constraints = [
        {
            "constraint_type": "min_payment",
            "value": {
                "amount": 1500,
                "currency": "USD",
                "duration_hours": 3,
                "hourly_rate": 500
            }
        },
        {
            "constraint_type": "pa_system_fee",
            "value": {"amount": 300, "currency": "USD"}
        },
        {
            "constraint_type": "min_notice_days",
            "value": {"days": 14}
        }
    ]
    
    constraints_text = get_booking_constraints_text(constraints)
    print(f"\nBooking Constraints:")
    print(constraints_text)
    
    context = {
        "venue_name": "The Basement",
        "proposed_dates": "March 20, 2025",
        "venue_offer": "$800 for 3-hour set, no PA needed",
        "band_availability": "All members available",
        "booking_constraints": constraints_text,
        "min_notice_days": 14,
        "max_shows_per_month": 8,
        "conversation_history": "Initial inquiry received yesterday"
    }
    
    prompt = format_prompt(NEGOTIATION_PROMPT, context)
    
    messages = [
        LLMMessage(role="system", content=BASE_SYSTEM_PROMPT),
        LLMMessage(role="system", content=prompt),
        LLMMessage(
            role="user",
            content="We'd love to book you for March 20th! We can offer $800 for a 3-hour set. You won't need to bring PA, we have everything set up."
        )
    ]
    
    response = await llm_service.generate(messages=messages, temperature=0.7, max_tokens=350)
    
    print(f"\nVenue Offer:")
    print("We'd love to book you for March 20th! We can offer $800 for a 3-hour set. You won't need to bring PA, we have everything set up.")
    print(f"\nAgent Response:")
    print(response.content)
    
    # Check if response mentions the correct rate
    if "1500" in response.content or "$1,500" in response.content:
        print("\n✅ GOOD: Agent correctly mentioned $1,500 rate")
    else:
        print("\n⚠️  WARNING: Agent might not have mentioned the correct $1,500 rate")
    
    print(f"\nTokens used: {response.usage}")


async def test_pa_system_pricing():
    """Test negotiation when band provides PA"""
    print("\n" + "="*60)
    print("TEST: Pricing with PA System Rental")
    print("="*60)
    
    constraints = [
        {
            "constraint_type": "min_payment",
            "value": {
                "amount": 1500,
                "currency": "USD",
                "duration_hours": 3,
                "hourly_rate": 500
            }
        },
        {
            "constraint_type": "pa_system_fee",
            "value": {"amount": 300, "currency": "USD"}
        }
    ]
    
    constraints_text = get_booking_constraints_text(constraints)
    
    context = {
        "venue_name": "The Dive Bar",
        "proposed_dates": "April 5, 2025",
        "venue_offer": "$1,500 for 3-hour set, band needs to bring PA",
        "band_availability": "All members available",
        "booking_constraints": constraints_text,
        "min_notice_days": 14,
        "max_shows_per_month": 8,
        "conversation_history": "Discussing equipment needs"
    }
    
    prompt = format_prompt(NEGOTIATION_PROMPT, context)
    
    messages = [
        LLMMessage(role="system", content=BASE_SYSTEM_PROMPT),
        LLMMessage(role="system", content=prompt),
        LLMMessage(
            role="user",
            content="We can do $1,500 for the 3-hour set on April 5th, but you'll need to bring your own PA system. Does that work?"
        )
    ]
    
    response = await llm_service.generate(messages=messages, temperature=0.7, max_tokens=350)
    
    print(f"\nVenue Offer:")
    print("We can do $1,500 for the 3-hour set on April 5th, but you'll need to bring your own PA system. Does that work?")
    print(f"\nAgent Response:")
    print(response.content)
    
    # Check if response mentions PA fee
    if "300" in response.content or "1,800" in response.content or "1800" in response.content:
        print("\n✅ GOOD: Agent correctly mentioned PA system fee")
    else:
        print("\n⚠️  WARNING: Agent might not have mentioned the $300 PA fee")
    
    print(f"\nTokens used: {response.usage}")


async def main():
    """Run pricing tests"""
    try:
        print("\n🧪 Testing Updated Pricing ($1,500 for 3 hours)\n")
        
        await test_updated_pricing()
        await test_pa_system_pricing()
        
        print("\n" + "="*60)
        print("✅ Pricing tests completed!")
        print("\nNext step: Run update_constraints.sql in Supabase to update the database")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
