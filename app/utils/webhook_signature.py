
import hmac
import hashlib
import base64
import structlog
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
        # Svix signatures can be separated by semicolons or spaces
        sig_candidates = []
        for part in signature.replace(';', ' ').split():
            if part.startswith('v1,'):
                sig_candidates.append(part[3:])
        logger.info("Parsed v1 signatures", candidates=sig_candidates)
        decoded_secret = base64.b64decode(secret)
        computed = hmac.new(
            key=decoded_secret,
            msg=payload,
            digestmod=hashlib.sha256
        ).digest()
        computed_b64 = base64.b64encode(computed).decode()
        logger.info("Computed signature", computed_signature=computed_b64)
        for sig in sig_candidates:
            logger.info("Comparing signatures", provided=sig, computed=computed_b64)
            if hmac.compare_digest(sig, computed_b64):
                logger.info("Signature match found")
                return True
        logger.error("No matching signature found", provided=sig_candidates, computed=computed_b64)
        return False
    except Exception as e:
        logger.error("Exception during signature verification", error=str(e))
        return False
