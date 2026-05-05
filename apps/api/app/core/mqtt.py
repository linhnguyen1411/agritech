"""MQTT publisher for IoT farm commands.

Each publish creates a fresh connection (fire-and-forget pattern suitable
for low-frequency commands like feeding). For high-throughput scenarios,
replace with a persistent `aiomqtt.Client` singleton held in app state.

Topic convention
----------------
/farm/nft/{chip_id}/feed      – trigger feed mechanism
/farm/nft/{chip_id}/status    – request device status (future)

QoS level 1 (at least once) is used for all commands.
"""
import json
import logging
from datetime import UTC, datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

# QoS 1 = at-least-once delivery (IoT command must reach device)
_QOS = 1


async def publish_feed_command(
    chip_id: str,
    chicken_id: str,
    nft_token_id: str | None,
    ordered_by_user_id: str,
    correlation_id: str,
    amount_grams: int = 50,
) -> bool:
    """Publish a feed command to the farm IoT broker.

    Returns True on success, False if MQTT is disabled or publish fails.
    Failures are logged but never raise – callers should not block on MQTT.
    """
    if not settings.MQTT_ENABLED:
        logger.debug("MQTT disabled – skipping publish for chip=%s", chip_id)
        return False

    topic = f"/farm/nft/{chip_id}/feed"
    payload = {
        "command": "feed",
        "chicken_id": chicken_id,
        "nft_token_id": nft_token_id,
        "chip_id": chip_id,
        "amount_grams": amount_grams,
        "ordered_by_user_id": ordered_by_user_id,
        "ordered_at": datetime.now(UTC).isoformat(),
        "correlation_id": correlation_id,
    }

    return await _publish(topic, payload)


async def _publish(topic: str, payload: dict) -> bool:
    try:
        import aiomqtt

        client_kwargs: dict = {
            "hostname": settings.MQTT_BROKER_HOST,
            "port": settings.MQTT_BROKER_PORT,
        }
        if settings.MQTT_USERNAME:
            client_kwargs["username"] = settings.MQTT_USERNAME
            client_kwargs["password"] = settings.MQTT_PASSWORD

        async with aiomqtt.Client(**client_kwargs) as client:
            await client.publish(topic, payload=json.dumps(payload), qos=_QOS)

        logger.info("MQTT published topic=%s correlation_id=%s", topic, payload.get("correlation_id"))
        return True

    except ImportError:
        logger.warning("aiomqtt not installed – MQTT publish skipped")
        return False
    except Exception as exc:
        logger.error("MQTT publish failed topic=%s error=%s", topic, exc)
        return False
