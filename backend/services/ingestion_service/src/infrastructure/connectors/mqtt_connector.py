import asyncio
import logging
import os
from typing import Callable, List, Awaitable

import aiomqtt

logger = logging.getLogger(__name__)


class MQTTConnector:
    """
    Async MQTT Connector using aiomqtt.
    Manages persistent connection, subscriptions, and delegates messages to an injected handler.
    """

    def __init__(self, message_handler: Callable[[str, bytes], Awaitable[None]]) -> None:
        self.host = os.environ.get("MQTT_HOST", "localhost")
        self.port = int(os.environ.get("MQTT_PORT", "1883"))
        self.username = os.environ.get("MQTT_USERNAME")
        self.password = os.environ.get("MQTT_PASSWORD")
        self.client_id = os.environ.get("MQTT_CLIENT_ID", "")
        
        topics_env = os.environ.get("MQTT_TOPICS", "factory/+/sensors/#")
        self.topics: List[str] = [t.strip() for t in topics_env.split(",") if t.strip()]
        
        self.message_handler = message_handler
        self._running = False

    async def connect(self) -> None:
        """
        Connects to the MQTT broker, subscribes to topics, and listens for messages.
        Implements automatic reconnect with exponential backoff.
        """
        self._running = True
        backoff = 1.0
        max_backoff = 30.0

        while self._running:
            try:
                logger.info("Connecting to MQTT broker %s:%d...", self.host, self.port)
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    client_id=self.client_id or None
                ) as client:
                    backoff = 1.0  # Reset backoff on successful connect
                    logger.info("Successfully connected to MQTT broker.")
                    
                    for topic in self.topics:
                        await client.subscribe(topic, qos=1)
                        logger.info("Subscribed to MQTT topic: %s", topic)

                    async for message in client.messages:
                        if not self._running:
                            break
                        try:
                            await self.message_handler(str(message.topic), message.payload)
                        except Exception as e:
                            logger.error("Error handling MQTT message on %s: %s", str(message.topic), str(e))
                            
            except aiomqtt.MqttError as e:
                logger.warning("MQTT connection error: %s. Reconnecting in %.1fs...", str(e), backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            except Exception as e:
                logger.error("Unexpected error in MQTT loop: %s", str(e))
                await asyncio.sleep(5.0)

    def disconnect(self) -> None:
        """
        Signals the connector to gracefully stop listening and disconnect.
        """
        logger.info("Disconnecting MQTT connector...")
        self._running = False
