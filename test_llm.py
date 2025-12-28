"""Quick test script for LLM service"""

import asyncio
from app.services.llm_service import llm_service, LLMMessage


async def test_basic_generation():
    """Test basic LLM generation"""
    print("Testing basic LLM generation...")
    
    messages = [
        LLMMessage(
            role="system",
            content="You are a helpful assistant for a band booking agent."
        ),
        LLMMessage(
            role="user",
            content="Say hello and introduce yourself in one sentence."
        ),
    ]
    
    response = await llm_service.generate(messages=messages, max_tokens=100)
    
    print(f"\nProvider: {response.provider}")
    print(f"Model: {response.model}")
    print(f"Response: {response.content}")
    print(f"Tokens used: {response.usage}")
    print(f"Finish reason: {response.finish_reason}")
    return response


async def test_intent_classification():
    """Test intent classification"""
    print("\n" + "="*60)
    print("Testing intent classification...")
    
    test_messages = [
        "Hi, I'd like to book your band for a show on March 15th at my venue",
        "I'm available that weekend, count me in!",
        "Can we move the show to 8pm instead of 7pm?",
        "Yes, I accept the contract terms",
        "Just following up on the booking we discussed last week",
    ]
    
    for msg in test_messages:
        intent = await llm_service.classify_intent(msg)
        print(f"\nMessage: {msg}")
        print(f"Intent: {intent}")


async def main():
    """Run all tests"""
    try:
        await test_basic_generation()
        await test_intent_classification()
        print("\n" + "="*60)
        print("✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
