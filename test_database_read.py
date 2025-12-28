"""Simple read-only database test"""

import asyncio
from app.services.supabase_client import supabase_client


async def test_read_operations():
    """Test read-only operations that don't require RLS bypass"""
    print("Testing read-only database operations...\n")
    
    # Test 1: Get band members
    print("1. Getting band members...")
    try:
        band_members = await supabase_client.get_band_members()
        print(f"   ✅ Found {len(band_members)} band members")
        for member in band_members:
            print(f"      - {member.get('name', 'N/A')} ({member.get('role', 'N/A')})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Get booking constraints
    print("\n2. Getting booking constraints...")
    try:
        constraints = await supabase_client.get_booking_constraints()
        print(f"   ✅ Found {len(constraints)} active constraints:")
        for constraint in constraints:
            ctype = constraint.get('constraint_type', 'unknown')
            value = constraint.get('value', {})
            print(f"      - {ctype}: {value}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("✅ Read-only tests completed!")
    print("\nNote: The service role key should allow writes, but RLS policies")
    print("may need adjustment. For now, the agent can read constraints and")
    print("band member data which is the critical foundation.")


async def main():
    try:
        await test_read_operations()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
