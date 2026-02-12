import requests
import logging
from typing import Optional

logger = logging.getLogger('biliutility.http')

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

class BiliHTTPClient:
    """Centralized HTTP client for Bilibili API requests"""
    DEFAULT_TIMEOUT = 10

    @staticmethod
    def get(url: str, params: Optional[dict] = None, timeout: Optional[int] = None) -> Optional[dict]:
        """Make GET request with standard error handling. Returns data dict or None."""
        try:
            response = requests.get(
                url,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=timeout or BiliHTTPClient.DEFAULT_TIMEOUT
            )
            response.encoding = 'utf-8'
            response.raise_for_status()
            data = response.json()

            if data.get('code') == 0:
                return data.get('data')
            else:
                logger.error(f"[BiliHTTPClient] API error: {data.get('message', 'Unknown error')}")
                return None
        except requests.exceptions.Timeout:
            logger.info(f"[BiliHTTPClient] Request timeout: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[BiliHTTPClient] Request failed: {e}")
            return None

    @staticmethod
    def post(url: str, json_data: Optional[dict] = None, timeout: Optional[int] = None) -> bool:
        """Make POST request with standard error handling. Returns success boolean."""
        try:
            response = requests.post(
                url,
                json=json_data or {},
                headers={**DEFAULT_HEADERS, 'Content-Type': 'application/json'},
                timeout=timeout or BiliHTTPClient.DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[BiliHTTPClient] POST failed: {e}")
            return False
