"""Test email service functionality"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Then import email service (so it picks up the env vars)
from app.services.email_service import EmailService

# Create service instance with loaded env vars
email_service = EmailService()


async def test_send_simple_email():
    """Test basic email sending"""
    print("="*60)
    print("TEST: Send Simple Email")
    print("="*60)
    
    # Check if we have the API key configured
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        print("\n⚠️  RESEND_API_KEY not set - skipping live test")
        print("Set RESEND_API_KEY environment variable to test email sending")
        return
    
    try:
        result = await email_service.send_email(
            to=["delivered@resend.dev"],  # Resend's test address
            subject="Test Email from Booking Agent",
            html="<h1>Hello!</h1><p>This is a test email from the Sick Day with Ferris booking agent.</p>",
            text="Hello! This is a test email from the Sick Day with Ferris booking agent.",
            metadata={
                "test": "true",
                "conversation_id": "test-123"
            }
        )
        
        print(f"\n✅ Email sent successfully!")
        print(f"Email ID: {result['email_id']}")
        print(f"Status: {result['status']}")
        print(f"Sent at: {result['sent_at']}")
        
    except Exception as e:
        print(f"\n❌ Failed to send email: {str(e)}")


async def test_send_booking_inquiry():
    """Test booking inquiry email template"""
    print("\n" + "="*60)
    print("TEST: Send Booking Inquiry")
    print("="*60)
    
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        print("\n⚠️  RESEND_API_KEY not set - skipping live test")
        return
    
    try:
        message_content = """We're a Chicago-based indie rock band and we'd love to play at The Basement!

We typically perform 3-hour sets with a mix of originals and covers. Our standard rate is $1,500 for a 3-hour performance.

We have availability on the following dates:
- March 15, 2026
- March 22, 2026
- March 29, 2026

Would any of these dates work for your venue? We can also bring our own PA system if needed (additional $300).

Looking forward to hearing from you!"""
        
        result = await email_service.send_booking_inquiry(
            venue_email="delivered@resend.dev",
            venue_name="The Basement",
            venue_contact_name="Sarah",
            message_content=message_content,
            conversation_id="conv-test-456",
            booking_id="booking-test-789"
        )
        
        print(f"\n✅ Booking inquiry sent successfully!")
        print(f"Email ID: {result['email_id']}")
        
    except Exception as e:
        print(f"\n❌ Failed to send booking inquiry: {str(e)}")


def test_process_webhook():
    """Test webhook payload processing"""
    print("\n" + "="*60)
    print("TEST: Process Inbound Email Webhook")
    print("="*60)
    
    # Simulate a Resend webhook payload for received email
    mock_payload = {
        "type": "email.received",
        "data": {
            "from": "Sarah Johnson <sarah@thebasement.com>",
            "to": ["agent@sickdaywithferris.band"],
            "subject": "Re: Booking Inquiry - March dates",
            "html": "<p>Hi! March 22nd works great for us. Can you send over the contract?</p>",
            "text": "Hi! March 22nd works great for us. Can you send over the contract?",
            "tags": [
                {"name": "conversation_id", "value": "conv-123"},
                {"name": "booking_id", "value": "booking-456"}
            ]
        }
    }
    
    try:
        parsed = email_service.process_inbound_webhook(mock_payload)
        
        print(f"\n✅ Webhook processed successfully!")
        print(f"Event Type: {parsed['event_type']}")
        print(f"From: {parsed['sender_name']} <{parsed['sender_email']}>")
        print(f"Subject: {parsed['subject']}")
        print(f"Content (text): {parsed['text_content'][:50]}...")
        print(f"Metadata: {parsed['metadata']}")
        
    except Exception as e:
        print(f"\n❌ Failed to process webhook: {str(e)}")


def test_webhook_status_event():
    """Test email status webhook processing"""
    print("\n" + "="*60)
    print("TEST: Process Email Status Webhook")
    print("="*60)
    
    mock_payload = {
        "type": "email.delivered",
        "data": {
            "email_id": "abc123def456",
            "to": "sarah@thebasement.com",
            "subject": "Booking Inquiry - Sick Day with Ferris"
        }
    }
    
    try:
        parsed = email_service.process_inbound_webhook(mock_payload)
        
        print(f"\n✅ Status webhook processed!")
        print(f"Event Type: {parsed['event_type']}")
        print(f"Email ID: {parsed['email_id']}")
        
    except Exception as e:
        print(f"\n❌ Failed to process status webhook: {str(e)}")


async def main():
    """Run all email service tests"""
    print("\n🧪 Testing Email Service\n")
    
    try:
        # Test basic sending
        await test_send_simple_email()
        
        # Test booking inquiry template
        await test_send_booking_inquiry()
        
        # Test webhook processing (no API key needed)
        test_process_webhook()
        test_webhook_status_event()
        
        print("\n" + "="*60)
        print("✅ Email service tests completed!")
        print("\nNext steps:")
        print("1. Set RESEND_API_KEY in .env file")
        print("2. Configure RESEND_FROM_ADDRESS (default: agent@sickdaywithferris.band)")
        print("3. Verify your domain in Resend dashboard")
        print("4. Set up webhook endpoint for receiving emails")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Tests failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
