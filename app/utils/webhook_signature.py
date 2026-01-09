

import structlog
from svix.webhooks import Webhook, WebhookVerificationError
from app.config import settings


def verify_svix_signature(payload: bytes, headers: dict, secret: str) -> bool:
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
    if not headers or not secret:
        logger.error("Missing headers or secret", headers=headers, secret=secret)
        return False
    try:
        wh = Webhook(secret)
        wh.verify(payload, headers)
        logger.info("Signature verified using svix-python library")
        return True
    except WebhookVerificationError as e:
        logger.error("Svix signature verification failed", error=str(e))
        return False
    except Exception as e:
        logger.error("Exception during signature verification", error=str(e))
        return False
