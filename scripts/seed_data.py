"""Seed script for local development — sample sensor readings."""

from __future__ import annotations

import asyncio
import datetime
import os

import asyncpg


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ikb_admin:ikb_secret_2024@postgres:5432/ikb_main",
)


async def seed() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    try:
        samples = [
            ("temperature", "CNC-07", "default", 42.5, "C", 100, now),
            ("vibration", "CNC-07", "default", 1.2, "mm/s", 100, now),
            ("pressure", "PUMP-03", "default", 3.8, "bar", 100, now),
        ]
        for row in samples:
            await conn.execute(
                """
                INSERT INTO sensor_readings
                    (sensor_id, machine_id, tenant_id, value, unit, quality, recorded_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                *row,
            )
        print(f"✅ Seed data applied ({len(samples)} sensor readings).")
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
