

import structlog
from svix.webhooks import Webhook, WebhookVerificationError
from app.config import settings


def verify_svix_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify the Svix (Resend) webhook signature.
    Args:
        payload: Raw request body (bytes)
        signature: Value of the 'Svix-Signature' header
        secret: Webhook signing secret from config
    Returns:
        True if signature is valid, False otherwise
    """
    logger = structlog.get_logger()
    if not signature or not secret:
        logger.error("Missing signature or secret", signature=signature, secret=secret)
        return False
    try:
        wh = Webhook(secret)
        # The svix library expects the payload as bytes and the signature header as a string
        wh.verify(payload, {"svix-signature": signature})
        logger.info("Signature verified using svix-python library")
        return True
    except WebhookVerificationError as e:
        logger.error("Svix signature verification failed", error=str(e))
        return False
    except Exception as e:
        logger.error("Exception during signature verification", error=str(e))
        return False
