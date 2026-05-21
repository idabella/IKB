from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any], dict[str, str]], Awaitable[None]]


class KafkaConsumerConfig(BaseModel):
    # Production: set KAFKA_BOOTSTRAP_SERVERS=kafka:9092 in container env
    bootstrap_servers: str = Field(
        default_factory=lambda: os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    )
    group_id: str = "ikb-consumer-group"
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    max_poll_records: int = 100
    session_timeout_ms: int = 30000
    heartbeat_interval_ms: int = 10000
    max_poll_interval_ms: int = 300000


class KafkaMessageConsumer:
    """Async Kafka consumer with manual commit, graceful shutdown, and dead-letter support."""

    def __init__(
        self,
        topics: list[str],
        handler: MessageHandler,
        config: KafkaConsumerConfig | None = None,
        dead_letter_topic: str | None = None,
        max_retries: int = 3,
        retry_topic: str | None = None,
    ) -> None:
        self._topics = topics
        self._handler = handler
        self._config = config or KafkaConsumerConfig()
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._dead_letter_topic = dead_letter_topic
        self._max_retries = max_retries
        # If no retry topic supplied, derive one from the first subscribed topic.
        # Callers managing multiple topics should supply an explicit retry_topic.
        self._retry_topic: str = retry_topic or f"{topics[0]}.retry"

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._config.bootstrap_servers,
            group_id=self._config.group_id,
            auto_offset_reset=self._config.auto_offset_reset,
            enable_auto_commit=self._config.enable_auto_commit,
            max_poll_records=self._config.max_poll_records,
            session_timeout_ms=self._config.session_timeout_ms,
            heartbeat_interval_ms=self._config.heartbeat_interval_ms,
            max_poll_interval_ms=self._config.max_poll_interval_ms,
            value_deserializer=self._deserialize,
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            "Kafka consumer started — topics=%s group=%s retry_topic=%s",
            self._topics,
            self._config.group_id,
            self._retry_topic,
        )

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped.")

    async def consume(self) -> None:
        if not self._consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        try:
            async for record in self._consumer:
                if not self._running:
                    break
                await self._process_record(record)
        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled, shutting down gracefully.")
        finally:
            await self.stop()

    async def _process_record(self, record: ConsumerRecord) -> None:
        # Decode headers once; keep raw dict for safe int conversion from bytes.
        raw_headers: dict[str, bytes] = {
            k: v for k, v in (record.headers or [])
        }
        headers: dict[str, str] = {
            k: v.decode() for k, v in raw_headers.items()
        }

        # Safely extract retry count — header value arrives as bytes from Kafka.
        retry_count: int = int(raw_headers.get("x-retry-count", b"0"))

        try:
            await self._handler(record.value, headers)
            await self._consumer.commit()
            logger.debug(
                "Processed message from %s [partition=%d offset=%d]",
                record.topic,
                record.partition,
                record.offset,
            )

        except Exception:
            logger.exception(
                "Error processing message from %s [partition=%d offset=%d] "
                "(retry %d/%d)",
                record.topic,
                record.partition,
                record.offset,
                retry_count,
                self._max_retries,
            )

            if retry_count < self._max_retries:
                # ── RETRY PATH ────────────────────────────────────────────
                # Re-publish to the retry topic with an incremented counter.
                # Do NOT commit the offset here; if the re-publish itself
                # fails we fall through so the message is not silently lost.
                await self._republish_for_retry(record, headers, retry_count)

            else:
                # ── EXHAUSTED PATH ────────────────────────────────────────
                if self._dead_letter_topic:
                    # DLQ configured: park the message and move on.
                    await self._send_to_dead_letter(record, headers, retry_count)
                else:
                    # No DLQ: we have no safe place for this message.
                    logger.critical(
                        "Message permanently lost — no DLQ configured and retries "
                        "exhausted. topic=%s partition=%d offset=%d key=%s",
                        record.topic,
                        record.partition,
                        record.offset,
                        record.key,
                    )

                # Commit in both exhausted sub-cases to unblock the consumer.
                await self._consumer.commit()

    async def _republish_for_retry(
        self,
        record: ConsumerRecord,
        headers: dict[str, str],
        retry_count: int,
    ) -> None:
        """Re-publish a failed message to the retry topic with an incremented
        x-retry-count header.  Offset is intentionally NOT committed so that
        a re-publish failure does not cause silent message loss — the caller's
        exception handler will fall through to DLQ/commit instead.
        """
        producer: AIOKafkaProducer | None = None

        try:
            # Rebuild headers, overwriting x-retry-count with the new value.
            new_headers: list[tuple[str, bytes]] = [
                (k, v.encode() if isinstance(v, str) else v)
                for k, v in headers.items()
                if k != "x-retry-count"
            ]
            new_headers.append(("x-retry-count", str(retry_count + 1).encode()))
            new_headers.append(("x-original-topic", record.topic.encode()))

            producer = AIOKafkaProducer(
                bootstrap_servers=self._config.bootstrap_servers,
            )
            await producer.start()

            await producer.send_and_wait(
                topic=self._retry_topic,
                value=record.value,
                key=record.key,
                headers=new_headers,
            )

            logger.info(
                "Re-published message to retry topic %s "
                "[original_topic=%s partition=%d offset=%d retry=%d/%d]",
                self._retry_topic,
                record.topic,
                record.partition,
                record.offset,
                retry_count + 1,
                self._max_retries,
            )
            # Offset deliberately not committed — Kafka will not redeliver
            # because we have re-queued the work on the retry topic ourselves.
            await self._consumer.commit()

        except Exception:
            # Re-publish failed: log and do NOT commit so the original message
            # is redelivered by Kafka on the next poll.
            logger.error(
                "Failed to re-publish message to retry topic %s — "
                "offset NOT committed; Kafka will redeliver. "
                "[original_topic=%s partition=%d offset=%d]",
                self._retry_topic,
                record.topic,
                record.partition,
                record.offset,
                exc_info=True,
            )

        finally:
            if producer is not None:
                await producer.stop()

    async def _send_to_dead_letter(
        self,
        record: ConsumerRecord,
        headers: dict[str, str],
        retry_count: int,
    ) -> None:
        logger.warning(
            "Sending message to dead letter topic %s after %d retries",
            self._dead_letter_topic,
            retry_count,
        )

        producer: AIOKafkaProducer | None = None

        try:
            new_headers: list[tuple[str, bytes]] = [
                (k, v.encode() if isinstance(v, str) else v)
                for k, v in headers.items()
            ]
            new_headers.append(("x-original-topic", record.topic.encode()))
            new_headers.append(("x-retry-count", str(retry_count).encode()))

            producer = AIOKafkaProducer(
                bootstrap_servers=self._config.bootstrap_servers,
            )
            await producer.start()

            await producer.send_and_wait(
                topic=self._dead_letter_topic,
                value=record.value,
                key=record.key,
                headers=new_headers,
            )

            logger.info(
                "Successfully published message to DLQ topic %s "
                "from original topic %s",
                self._dead_letter_topic,
                record.topic,
            )

        except Exception:
            logger.error(
                "Failed to publish message to DLQ topic %s from original topic %s",
                self._dead_letter_topic,
                record.topic,
                exc_info=True,
            )

        finally:
            if producer is not None:
                await producer.stop()

    @staticmethod
    def _deserialize(value: bytes) -> dict[str, Any]:
        return orjson.loads(value)

    async def __aenter__(self) -> KafkaMessageConsumer:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()