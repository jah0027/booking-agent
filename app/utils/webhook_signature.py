import hmac
import hashlib
import base64
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
    if not signature or not secret:
        return False
    try:
        # Svix signatures are in the format: v1,<sig1>;v1,<sig2>;...
        for sig_part in signature.split(';'):
            if sig_part.startswith('v1,'):
                sig = sig_part[3:]
                computed = hmac.new(
                    key=base64.b64decode(secret),
                    msg=payload,
                    digestmod=hashlib.sha256
                ).digest()
                computed_b64 = base64.b64encode(computed).decode()
                if hmac.compare_digest(sig, computed_b64):
                    return True
        return False
    except Exception:
        return False
