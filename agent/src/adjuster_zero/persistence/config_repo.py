"""Load the active routing config (thresholds) from the versioned config table.

Falls back to RoutingConfig() defaults when no DB is configured, so the graph
runs locally without Supabase. Returns (config, config_version) so every routing
decision records the version that produced it (reproducibility).
"""

from __future__ import annotations

from .. import db
from ..router import RoutingConfig


async def load_routing_config() -> tuple[RoutingConfig, int | None]:
    pool = db.get_pool()
    if pool is None:
        return RoutingConfig(), None
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT version, value FROM config "
                "WHERE key = 'routing' AND active = true "
                "ORDER BY version DESC LIMIT 1"
            )
            row = await cur.fetchone()
    if row is None:
        return RoutingConfig(), None
    version, value = row
    return RoutingConfig.model_validate(value), int(version)
