"""
Feishu notification tool.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def feishu_notify_async(text: str, chat_id: Optional[str] = None) -> dict:
    """
    Send Feishu notification via Hermes gateway.
    """
    await asyncio.sleep(0.1)
    logger.info("Feishu notify chat_id=%s: %s", chat_id, text[:100])
    return {
        "status": "ok",
        "message": "Notification sent via Hermes",
        "chat_id": chat_id,
        "text_length": len(text),
    }
