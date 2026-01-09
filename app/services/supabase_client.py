"""Supabase database client"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional
from uuid import UUID

from supabase import create_client, Client
import structlog

from app.config import settings

logger = structlog.get_logger()


class SupabaseClient:
    """Wrapper for Supabase client operations"""

    def __init__(self):
        # Use synchronous client - service role key bypasses RLS automatically
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
        logger.info("supabase_client_initialized")

    def get_client(self) -> Client:
        """Get Supabase client instance"""
        return self.client

    async def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get contact by email address"""
        try:
            result = self.client.table("contacts").select("*").eq("email", email).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error("get_contact_by_email_failed", error=str(e), email=email)
            return None

    async def create_contact(self, email: str, name: str = "") -> Optional[str]:
        """Create a new contact and return its ID"""
        try:
            result = self.client.table("contacts").insert({"email": email, "name": name}).execute()
            contact_id = result.data[0]["id"] if result.data else None
            logger.info("contact_created", contact_id=contact_id, email=email)
            return contact_id
        except Exception as e:
            logger.error("create_contact_failed", error=str(e), email=email)
            return None

    # ===== CONVERSATIONS =====

    async def create_conversation(
        self,
        channel: str = "email",
        participants: Optional[List[Dict[str, Any]]] = None,
        related_booking_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new conversation"""
        try:
            result = self.client.table("conversations").insert({
                "channel": channel,
                "participants": participants or [],
                "related_booking_id": related_booking_id,
                "metadata": metadata or {},
                "status": "active"
            }).execute()
            
            logger.info(
                "conversation_created",
                conversation_id=result.data[0]["id"],
                channel=channel
            )
            return result.data[0]
        except Exception as e:
            logger.error("create_conversation_failed", error=str(e))
            raise
    
    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation by ID"""
        try:
            result = self.client.table("conversations").select("*").eq("id", conversation_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error("get_conversation_failed", error=str(e), conversation_id=conversation_id)
            raise
    
    async def get_conversations_by_participant(self, email: str) -> List[Dict[str, Any]]:
        """Get active conversations for a participant email"""
        try:
            result = (
                self.client.table("conversations")
                .select("*")
                .eq("status", "active")
                .order("created_at", desc=True)
                .execute()
            )
            # Filter in Python since JSONB queries can be complex
            conversations = []
            for conv in result.data:
                participants = conv.get("participants", [])
                if any(p.get("email") == email for p in participants):
                    conversations.append(conv)
            return conversations
        except Exception as e:
            logger.error("get_conversation_by_email_failed", error=str(e), email=email)
            raise
    
    async def update_conversation_status(
        self,
        conversation_id: str,
        status: str
    ) -> Dict[str, Any]:
        """Update conversation status"""
        try:
            result = (
                self.client.table("conversations")
                .update({"status": status})
                .eq("id", conversation_id)
                .execute()
            )
            logger.info("conversation_status_updated", conversation_id=conversation_id, status=status)
            return result.data[0]
        except Exception as e:
            logger.error("update_conversation_status_failed", error=str(e))
            raise
    
    # ===== MESSAGES =====
    
    async def create_message(
        self,
        conversation_id: str,
        sender_type: str,
        sender_id: str,
        content: str,
        sender_name: Optional[str] = None,
        role: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a message in a conversation"""
        try:
            result = self.client.table("messages").insert({
                "conversation_id": conversation_id,
                "sender_type": sender_type,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "content": content,
                "role": role,
                "metadata": metadata or {}
            }).execute()
            
            logger.info(
                "message_created",
                message_id=result.data[0]["id"],
                conversation_id=conversation_id,
                role=role
            )
            return result.data[0]
        except Exception as e:
            logger.error("create_message_failed", error=str(e))
            raise
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all messages for a conversation"""
        try:
            result = (
                self.client.table("messages")
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error("get_conversation_messages_failed", error=str(e))
            raise
    
    # ===== BOOKINGS =====
    
    async def create_booking(
        self,
        venue_id: Optional[str],
        proposed_dates: Optional[List[Dict[str, Any]]] = None,
        agreed_date: Optional[date] = None,
        terms: Optional[Dict[str, Any]] = None,
        status: str = "collecting_availability"
    ) -> Dict[str, Any]:
        """Create a new booking"""
        try:
            result = self.client.table("bookings").insert({
                "venue_id": venue_id,
                "proposed_dates": proposed_dates or [],
                "agreed_date": agreed_date.isoformat() if agreed_date else None,
                "terms": terms or {},
                "status": status
            }).execute()
            
            logger.info(
                "booking_created",
                booking_id=result.data[0]["id"],
                event_date=event_date.isoformat()
            )
            return result.data[0]
        except Exception as e:
            logger.error("create_booking_failed", error=str(e))
            raise
    
    async def get_booking(self, booking_id: str) -> Optional[Dict[str, Any]]:
        """Get booking by ID"""
        try:
            result = self.client.table("bookings").select("*").eq("id", booking_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error("get_booking_failed", error=str(e))
            raise
    
    async def update_booking_status(
        self,
        booking_id: str,
        status: str
    ) -> Dict[str, Any]:
        """Update booking status"""
        try:
            result = (
                self.client.table("bookings")
                .update({"status": status})
                .eq("id", booking_id)
                .execute()
            )
            logger.info("booking_status_updated", booking_id=booking_id, status=status)
            return result.data[0]
        except Exception as e:
            logger.error("update_booking_status_failed", error=str(e))
            raise
    
    async def check_booking_conflicts(
        self,
        event_date: date,
        exclude_booking_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Check for booking conflicts on a given date"""
        try:
            query = (
                self.client.table("bookings")
                .select("*")
                .eq("agreed_date", event_date.isoformat())
                .in_("status", ["negotiating", "pending_approval", "confirmed"])
            )
            
            if exclude_booking_id:
                query = query.neq("id", exclude_booking_id)
            
            result = query.execute()
            return result.data
        except Exception as e:
            logger.error("check_booking_conflicts_failed", error=str(e))
            raise
    
    # ===== AVAILABILITY =====
    
    async def create_availability(
        self,
        band_member_id: str,
        date_range_start: date,
        date_range_end: date,
        status: str = "available",
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create availability entry"""
        try:
            result = self.client.table("availability").insert({
                "band_member_id": band_member_id,
                "date_range_start": date_range_start.isoformat(),
                "date_range_end": date_range_end.isoformat(),
                "status": status,
                "notes": notes
            }).execute()
            
            logger.info(
                "availability_created",
                availability_id=result.data[0]["id"],
                band_member_id=band_member_id
            )
            return result.data[0]
        except Exception as e:
            logger.error("create_availability_failed", error=str(e))
            raise
    
    async def check_band_availability(
        self,
        event_date: date
    ) -> List[Dict[str, Any]]:
        """Check which band members are available on a date"""
        try:
            result = (
                self.client.table("availability")
                .select("*, band_members(*)")
                .lte("date_range_start", event_date.isoformat())
                .gte("date_range_end", event_date.isoformat())
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error("check_band_availability_failed", error=str(e))
            raise
    
    async def get_band_members(self) -> List[Dict[str, Any]]:
        """Get all active band members"""
        try:
            result = (
                self.client.table("band_members")
                .select("*")
                .eq("active", True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error("get_band_members_failed", error=str(e))
            raise
    
    # ===== CONTRACTS =====
    
    async def create_contract(
        self,
        booking_id: str,
        populated_fields: Dict[str, Any],
        template_name: str = "standard",
        approval_status: str = "draft"
    ) -> Dict[str, Any]:
        """Create a contract for a booking"""
        try:
            result = self.client.table("contracts").insert({
                "booking_id": booking_id,
                "template_name": template_name,
                "populated_fields": populated_fields,
                "approval_status": approval_status
            }).execute()
            
            logger.info(
                "contract_created",
                contract_id=result.data[0]["id"],
                booking_id=booking_id
            )
            return result.data[0]
        except Exception as e:
            logger.error("create_contract_failed", error=str(e))
            raise
    
    async def update_contract_status(
        self,
        contract_id: str,
        approval_status: str,
        approved_by: Optional[str] = None,
        approved_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Update contract status"""
        try:
            update_data = {"approval_status": approval_status}
            if approved_by:
                update_data["approved_by"] = approved_by
            if approved_at:
                update_data["approved_at"] = approved_at.isoformat()
            
            result = (
                self.client.table("contracts")
                .update(update_data)
                .eq("id", contract_id)
                .execute()
            )
            logger.info("contract_status_updated", contract_id=contract_id, status=approval_status)
            return result.data[0]
        except Exception as e:
            logger.error("update_contract_status_failed", error=str(e))
            raise
    
    # ===== BOOKING CONSTRAINTS =====
    
    async def get_booking_constraints(self) -> List[Dict[str, Any]]:
        """Get all active booking constraints"""
        try:
            result = (
                self.client.table("booking_constraints")
                .select("*")
                .eq("active", True)
                .execute()
            )
            return result.data
        except Exception as e:
            logger.error("get_booking_constraints_failed", error=str(e))
            raise


# Global Supabase client instance
supabase_client = SupabaseClient()


def get_supabase() -> Client:
    """Dependency for getting Supabase client in routes"""
    return supabase_client.get_client()
