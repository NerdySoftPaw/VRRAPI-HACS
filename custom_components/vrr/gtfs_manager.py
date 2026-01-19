"""GTFS Manager - Singleton manager for GTFS data instances.

This module provides a centralized manager for GTFS Static data instances
to prevent race conditions, memory leaks, and duplicate downloads.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Optional

from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from .gtfs_static import GTFSStaticData

_LOGGER = logging.getLogger(__name__)

# Module-level singleton instance
_manager_instance: Optional["GTFSManager"] = None
_manager_lock = asyncio.Lock()


class GTFSManager:
    """Singleton manager for GTFS Static data instances.

    This class manages GTFS data instances using reference counting
    to ensure proper cleanup and prevent memory leaks.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the GTFS Manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._instances: Dict[str, "GTFSStaticData"] = {}
        self._ref_counts: Dict[str, int] = {}
        self._registry_lock = asyncio.Lock()
        self._download_tasks: Dict[str, asyncio.Task] = {}
        self._shutting_down = False
        _LOGGER.debug("GTFSManager initialized")

    @classmethod
    async def get_instance(cls, hass: HomeAssistant) -> "GTFSManager":
        """Get or create the singleton GTFSManager instance.

        Args:
            hass: Home Assistant instance

        Returns:
            The GTFSManager singleton instance
        """
        global _manager_instance

        async with _manager_lock:
            if _manager_instance is None:
                _manager_instance = cls(hass)
                # Store in hass.data for access during cleanup
                hass.data.setdefault(DOMAIN, {})
                hass.data[DOMAIN]["gtfs_manager"] = _manager_instance
                _LOGGER.info("Created new GTFSManager instance")
            return _manager_instance

    @classmethod
    def get_instance_sync(cls, hass: HomeAssistant) -> Optional["GTFSManager"]:
        """Get the existing GTFSManager instance synchronously (if exists).

        Args:
            hass: Home Assistant instance

        Returns:
            The GTFSManager instance or None if not initialized
        """
        return hass.data.get(DOMAIN, {}).get("gtfs_manager")

    async def get_gtfs_data(self, provider: str) -> Optional["GTFSStaticData"]:
        """Get or create a GTFS Static data instance for a provider.

        Uses lazy initialization and reference counting.

        Args:
            provider: The provider identifier (e.g., "nta_ie", "gtfs_de")

        Returns:
            GTFSStaticData instance or None if shutting down
        """
        if self._shutting_down:
            _LOGGER.warning("GTFSManager is shutting down, cannot provide GTFS data")
            return None

        async with self._registry_lock:
            # Double-check after acquiring lock (shutdown might have started)
            if self._shutting_down:
                _LOGGER.warning("GTFSManager is shutting down, cannot provide GTFS data")
                return None

            if provider in self._instances:
                # Increment reference count
                self._ref_counts[provider] = self._ref_counts.get(provider, 0) + 1
                _LOGGER.debug(
                    "Reusing existing GTFS instance for %s (ref_count: %d)",
                    provider,
                    self._ref_counts[provider],
                )
                return self._instances[provider]

            # Create new instance
            # Import here to avoid circular imports
            from .gtfs_static import GTFSStaticData

            _LOGGER.info("Creating new GTFS instance for provider: %s", provider)
            instance = GTFSStaticData(self.hass, provider=provider, manager=self)
            self._instances[provider] = instance
            self._ref_counts[provider] = 1

            return instance

    async def release_gtfs_data(self, provider: str) -> None:
        """Release a reference to a GTFS Static data instance.

        When reference count reaches zero, the instance is cleaned up.

        Args:
            provider: The provider identifier
        """
        async with self._registry_lock:
            if provider not in self._instances:
                _LOGGER.warning("Attempted to release non-existent GTFS instance: %s", provider)
                return

            self._ref_counts[provider] = self._ref_counts.get(provider, 1) - 1
            _LOGGER.debug(
                "Released GTFS instance for %s (ref_count: %d)",
                provider,
                self._ref_counts[provider],
            )

            if self._ref_counts[provider] <= 0:
                await self._cleanup_instance(provider)

    async def _cleanup_instance(self, provider: str) -> None:
        """Clean up a GTFS instance and release memory.

        Args:
            provider: The provider identifier
        """
        _LOGGER.info("Cleaning up GTFS instance for provider: %s", provider)

        # Cancel any pending download task
        if provider in self._download_tasks:
            task = self._download_tasks.pop(provider)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    _LOGGER.debug("Cancelled download task for %s", provider)

        # Clear instance data
        if provider in self._instances:
            instance = self._instances.pop(provider)
            await instance.clear_data()

        self._ref_counts.pop(provider, None)

    def register_download_task(self, provider: str, task: asyncio.Task) -> None:
        """Register a download task for tracking and cancellation.

        Args:
            provider: The provider identifier
            task: The download task to track
        """
        # Cancel any existing task for this provider
        if provider in self._download_tasks:
            old_task = self._download_tasks[provider]
            if not old_task.done():
                old_task.cancel()

        self._download_tasks[provider] = task
        _LOGGER.debug("Registered download task for %s", provider)

    def unregister_download_task(self, provider: str) -> None:
        """Unregister a completed download task.

        Args:
            provider: The provider identifier
        """
        self._download_tasks.pop(provider, None)

    def is_shutting_down(self) -> bool:
        """Check if the manager is shutting down.

        Returns:
            True if shutdown is in progress
        """
        return self._shutting_down

    async def shutdown(self) -> None:
        """Shutdown the manager and cleanup all resources."""
        _LOGGER.info("GTFSManager shutting down...")
        self._shutting_down = True

        async with self._registry_lock:
            # Cancel all download tasks
            for provider, task in list(self._download_tasks.items()):
                if not task.done():
                    _LOGGER.debug("Cancelling download task for %s", provider)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            self._download_tasks.clear()

            # Clear all instances
            for provider in list(self._instances.keys()):
                instance = self._instances.pop(provider)
                await instance.clear_data()
                _LOGGER.debug("Cleared GTFS instance for %s", provider)

            self._ref_counts.clear()

        _LOGGER.info("GTFSManager shutdown complete")

    @property
    def active_providers(self) -> list:
        """Get list of active provider identifiers.

        Returns:
            List of provider identifiers with active instances
        """
        return list(self._instances.keys())

    def get_stats(self) -> Dict[str, any]:
        """Get manager statistics for debugging.

        Returns:
            Dictionary with manager statistics
        """
        return {
            "active_providers": self.active_providers,
            "ref_counts": dict(self._ref_counts),
            "pending_downloads": list(self._download_tasks.keys()),
            "shutting_down": self._shutting_down,
        }


async def get_gtfs_manager(hass: HomeAssistant) -> GTFSManager:
    """Convenience function to get the GTFSManager instance.

    Args:
        hass: Home Assistant instance

    Returns:
        The GTFSManager singleton instance
    """
    return await GTFSManager.get_instance(hass)


async def shutdown_gtfs_manager(hass: HomeAssistant) -> None:
    """Shutdown the GTFSManager if it exists.

    Args:
        hass: Home Assistant instance
    """
    global _manager_instance

    async with _manager_lock:
        manager = GTFSManager.get_instance_sync(hass)
        if manager:
            await manager.shutdown()
            _manager_instance = None
            hass.data.get(DOMAIN, {}).pop("gtfs_manager", None)
            _LOGGER.info("GTFSManager instance removed")
