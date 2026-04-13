"""
EventBus in-memory — remplace Redis pub/sub quand LOCAL_MODE=true.
Utilisé par les WebSockets pour diffuser les alertes et détections
sans aucune dépendance externe.
"""
import asyncio
import json
from collections import defaultdict
from typing import AsyncGenerator


class InMemoryEventBus:
    """
    Bus d'événements async in-process.
    Chaque subscriber reçoit sa propre Queue asyncio.
    Thread-safe pour les publications depuis des threads externes (service vidéo).
    """

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def publish(self, channel: str, data: dict | str):
        """Publie un message sur un canal (async)."""
        payload = json.dumps(data) if isinstance(data, dict) else data
        dead = []
        for queue in self._subscribers.get(channel, []):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(queue)
        for q in dead:
            self._subscribers[channel].remove(q)

    def publish_sync(self, channel: str, data: dict | str):
        """Publie depuis un thread non-async (camera_manager, etc.)."""
        payload = json.dumps(data) if isinstance(data, dict) else data
        loop = self._get_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.publish(channel, payload), loop
            )

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        """
        Générateur async — yield chaque message reçu sur le canal.
        Usage :
            async for message in event_bus.subscribe("alerts"):
                await websocket.send_text(message)
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[channel].append(queue)
        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            try:
                self._subscribers[channel].remove(queue)
            except ValueError:
                pass

    def subscriber_count(self, channel: str) -> int:
        return len(self._subscribers.get(channel, []))


# Singleton partagé entre tous les modules
event_bus = InMemoryEventBus()


# ── Abstraction unifiée Redis / In-memory ────────────────────

class EventBusAdapter:
    """
    Façade qui choisit automatiquement Redis ou InMemoryEventBus
    selon la variable d'environnement LOCAL_MODE.
    """
    import os
    _local_mode = os.getenv("LOCAL_MODE", "false").lower() == "true"

    def __init__(self):
        self._redis = None
        self._memory = event_bus

    async def init(self, redis_url: str | None = None):
        if self._local_mode or not redis_url:
            return

        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
            await self._redis.ping()
        except Exception:
            import warnings
            warnings.warn("Redis inaccessible → basculement sur EventBus in-memory")
            self._redis = None

    @property
    def is_local(self) -> bool:
        return self._redis is None

    async def publish(self, channel: str, data: dict | str):
        if self._redis:
            payload = data if isinstance(data, str) else __import__("json").dumps(data)
            await self._redis.publish(channel, payload)
        else:
            await self._memory.publish(channel, data)

    def publish_sync(self, channel: str, data: dict | str):
        """Depuis un thread non-async."""
        if self._redis is None:
            self._memory.publish_sync(channel, data)

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        if self._redis:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield message["data"]
        else:
            async for message in self._memory.subscribe(channel):
                yield message


# Instance globale
bus = EventBusAdapter()
