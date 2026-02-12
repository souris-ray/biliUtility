import logging
import time
from app.state import member_config, credentials_manager
from app.infrastructure.http_client import BiliHTTPClient

logger = logging.getLogger('biliutility.webhook')

class WebhookService:
    """Service for handling webhook triggers"""

    @staticmethod
    def trigger_webhook(webhook_type: str) -> bool:
        """Trigger a webhook with the specified type.
        
        Only triggers if webhooks are enabled for that specific tier.
        """
        # Check if enabled for this type
        if webhook_type == 'captain' and not member_config.enable_webhook_captain:
            return False
        if webhook_type == 'admiral' and not member_config.enable_webhook_admiral:
            return False
        if webhook_type == 'governor' and not member_config.enable_webhook_governor:
            return False
            
        webhook_urls = credentials_manager.get_webhook_urls()
        if webhook_type not in webhook_urls:
            return False

        webhook_url = webhook_urls[webhook_type]
        if not webhook_url:
            logger.info(f"[Webhook] No URL configured for {webhook_type}")
            return False

        logger.info(f"[Webhook] Triggering {webhook_type} webhook")
        # Post relies on requests which is synchronous.
        # Ideally this should be async, but for now we keep it sync or wrap it ?
        # BiliHTTPClient.post uses requests. 
        # If we are in an async context (TTSProcessor), calling this will block the loop.
        # We should probably wrap BiliHTTPClient.post in run_in_executor in the caller or here.
        # But BiliHTTPClient is infrastructure.
        # Let's trust the caller (TTSProcessor) to handle async wrapping if needed,
        # OR just block for a few ms (requests might block longer).
        return BiliHTTPClient.post(webhook_url)
