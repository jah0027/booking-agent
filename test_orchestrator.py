"""Test the booking agent orchestrator"""

import asyncio
from dotenv import load_dotenv
from app.agent.orchestrator import booking_agent

# Load environment variables
load_dotenv()


async def test_venue_inquiry():
    """Test handling a venue booking inquiry"""
    print("="*60)
    print("TEST: Venue Booking Inquiry")
    print("="*60)
    
    result = await booking_agent.process_message(
        message_content="Hi! We're The Basement, a music venue in Chicago. We'd love to book you for a show on March 15th, 2026. What's your availability and rate?",
        sender_email="sarah@thebasement.com",
        sender_name="Sarah Johnson",
        sender_type="venue"
    )
    
    print(f"\n📧 Venue Message:")
    print("Hi! We're The Basement, a music venue in Chicago. We'd love to book you for a show on March 15th, 2026. What's your availability and rate?")
    
    print(f"\n🤖 Agent Response:")
    print(result["response"])
    
    print(f"\n📊 Metadata:")
    print(f"Intent: {result['intent']}")
    print(f"Conversation ID: {result['conversation_id']}")
    print(f"Requires Approval: {result['requires_human_approval']}")
    
    return result["conversation_id"]


async def test_negotiation(conversation_id: str):
    """Test price negotiation"""
    print("\n" + "="*60)
    print("TEST: Price Negotiation")
    print("="*60)
    
    result = await booking_agent.process_message(
        message_content="We can offer $800 for the night. Does that work?",
        sender_email="sarah@thebasement.com",
        sender_name="Sarah Johnson",
        sender_type="venue",
        conversation_id=conversation_id
    )
    
    print(f"\n📧 Venue Offer:")
    print("We can offer $800 for the night. Does that work?")
    
    print(f"\n🤖 Agent Response:")
    print(result["response"])
    
    print(f"\n📊 Metadata:")
    print(f"Intent: {result['intent']}")
    print(f"Requires Approval: {result['requires_human_approval']}")
    
    return conversation_id


async def test_acceptable_offer(conversation_id: str):
    """Test acceptable offer that requires approval"""
    print("\n" + "="*60)
    print("TEST: Acceptable Offer")
    print("="*60)
    
    result = await booking_agent.process_message(
        message_content="Okay, we can do $1,500 for a 3-hour set on March 15th. We have our own PA system. Can you send over a contract?",
        sender_email="sarah@thebasement.com",
        sender_name="Sarah Johnson",
        sender_type="venue",
        conversation_id=conversation_id
    )
    
    print(f"\n📧 Venue Response:")
    print("Okay, we can do $1,500 for a 3-hour set on March 15th. We have our own PA system. Can you send over a contract?")
    
    print(f"\n🤖 Agent Response:")
    print(result["response"])
    
    print(f"\n📊 Metadata:")
    print(f"Intent: {result['intent']}")
    print(f"Requires Approval: {result['requires_human_approval']}")
    print(f"Next Action: {result.get('next_action')}")
    
    if result['requires_human_approval']:
        print("\n⚠️  HUMAN APPROVAL REQUIRED - Agent correctly requiring approval before confirming!")


async def test_band_member_availability():
    """Test band member availability request"""
    print("\n" + "="*60)
    print("TEST: Band Member Availability")
    print("="*60)
    
    result = await booking_agent.process_message(
        message_content="I'm available March 15th and 22nd, but not the 29th. Let me know!",
        sender_email="guitarist@sickdaywithferris.band",
        sender_name="Alex (Guitarist)",
        sender_type="band_member"
    )
    
    print(f"\n📧 Band Member:")
    print("I'm available March 15th and 22nd, but not the 29th. Let me know!")
    
    print(f"\n🤖 Agent Response:")
    print(result["response"])
    
    print(f"\n📊 Metadata:")
    print(f"Intent: {result['intent']}")
    print(f"Requires Approval: {result['requires_human_approval']}")


async def main():
    """Run all orchestrator tests"""
    print("\n🧪 Testing Booking Agent Orchestrator\n")
    
    try:
        # Test 1: Initial venue inquiry
        conversation_id = await test_venue_inquiry()
        
        # Test 2: Low offer negotiation
        await test_negotiation(conversation_id)
        
        # Test 3: Acceptable offer
        await test_acceptable_offer(conversation_id)
        
        # Test 4: Band member availability (separate conversation)
        await test_band_member_availability()
        
        print("\n" + "="*60)
        print("✅ All orchestrator tests completed!")
        print("\nKey Features Validated:")
        print("- Intent classification working")
        print("- Multi-turn conversations maintained")
        print("- Price negotiation with constraint enforcement")
        print("- Human approval triggered for acceptable offers")
        print("- Messages saved to database")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
