"""Test database CRUD operations"""

import asyncio
from datetime import date, datetime
from app.services.supabase_client import supabase_client


async def test_database_operations():
    """Test basic database operations"""
    print("Testing database operations...\n")
    
    # Test 1: Get band members
    print("1. Getting band members...")
    band_members = await supabase_client.get_band_members()
    print(f"   Found {len(band_members)} band members:")
    for member in band_members:
        print(f"   - {member['name']} ({member.get('role', 'N/A')}) - {member['email']}")
    
    # Test 2: Get booking constraints
    print("\n2. Getting booking constraints...")
    constraints = await supabase_client.get_booking_constraints()
    print(f"   Found {len(constraints)} active constraints:")
    for constraint in constraints:
        print(f"   - {constraint['constraint_type']}: {constraint['value']}")
    
    # Test 3: Check availability for a date
    print("\n3. Checking band availability for March 15, 2025...")
    test_date = date(2025, 3, 15)
    availability = await supabase_client.check_band_availability(test_date)
    print(f"   Found {len(availability)} availability entries")
    
    # Test 4: Create a test conversation
    print("\n4. Creating test conversation...")
    conversation = await supabase_client.create_conversation(
        channel="email",
        participants=[{"email": "test@venue.com", "name": "Test Venue", "type": "venue"}],
        metadata={"test": True}
    )
    print(f"   ✅ Created conversation: {conversation['id']}")
    
    # Test 5: Create a test message
    print("\n5. Creating test message...")
    message = await supabase_client.create_message(
        conversation_id=conversation['id'],
        sender_type="venue",
        sender_id="test@venue.com",
        sender_name="Test Venue",
        content="Hi, I'd like to book your band for March 15th!",
        role="user",
        metadata={"test": True}
    )
    print(f"   ✅ Created message: {message['id']}")
    
    # Test 6: Get messages for conversation
    print("\n6. Retrieving conversation messages...")
    messages = await supabase_client.get_conversation_messages(conversation['id'])
    print(f"   Found {len(messages)} messages")
    for msg in messages:
        print(f"   - [{msg['sender_type']}]: {msg['content'][:50]}...")
    
    # Test 7: Check for booking conflicts
    print("\n7. Checking for booking conflicts on March 15, 2025...")
    conflicts = await supabase_client.check_booking_conflicts(test_date)
    print(f"   Found {len(conflicts)} existing bookings on that date")
    
    # Test 8: Update conversation status
    print("\n8. Updating conversation status to resolved...")
    updated_conv = await supabase_client.update_conversation_status(
        conversation['id'],
        "resolved"
    )
    print(f"   ✅ Conversation status: {updated_conv['status']}")
    
    print("\n" + "="*60)
    print("✅ All database tests completed successfully!")
    print(f"Test conversation ID: {conversation['id']}")
    print("(You can clean this up manually in Supabase if needed)")


async def main():
    try:
        await test_database_operations()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
