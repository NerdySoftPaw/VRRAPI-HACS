"""GTFS Static data loader for NTA Ireland."""

import asyncio
import csv
import io
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
from aiofiles import open as aio_open
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE_URL_NTA_GTFS_STATIC, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Cache GTFS Static data for 24 hours
GTFS_CACHE_DURATION = timedelta(hours=24)


class GTFSStaticData:
    """Class to manage GTFS Static data loading and caching."""

    def __init__(self, hass: HomeAssistant):
        """Initialize GTFS Static data loader."""
        self.hass = hass
        self.stops: Dict[str, Dict[str, str]] = {}  # stop_id -> stop data
        self.routes: Dict[str, Dict[str, str]] = {}  # route_id -> route data
        self.trips: Dict[str, Dict[str, str]] = {}  # trip_id -> trip data
        self.stop_times: Dict[str, List[Dict[str, str]]] = {}  # trip_id -> list of stop_times
        self._cache_path = Path(hass.config.config_dir) / ".storage" / DOMAIN / "gtfs_static.zip"
        self._cache_timestamp_path = Path(hass.config.config_dir) / ".storage" / DOMAIN / "gtfs_static_timestamp.txt"
        self._last_update: Optional[datetime] = None

    async def ensure_loaded(self) -> bool:
        """Ensure GTFS Static data is loaded (download if needed)."""
        # Check if we need to download/update
        if await self._should_update():
            if not await self._download_and_load():
                return False

        # Load from cache if not already loaded
        if not self.stops and self._cache_path.exists():
            return await self._load_from_cache()

        return len(self.stops) > 0

    async def _should_update(self) -> bool:
        """Check if GTFS Static data should be updated."""
        # If cache doesn't exist, we need to download
        if not self._cache_path.exists():
            return True

        # Check timestamp
        if self._cache_timestamp_path.exists():
            try:
                async with aio_open(self._cache_timestamp_path, "r") as f:
                    timestamp_str = await f.read()
                    last_update = datetime.fromisoformat(timestamp_str.strip())
                    if datetime.now() - last_update < GTFS_CACHE_DURATION:
                        return False
            except Exception as e:
                _LOGGER.warning("Error reading cache timestamp: %s", e)
                return True

        return True

    async def _download_and_load(self) -> bool:
        """Download GTFS Static ZIP and load data."""
        _LOGGER.info("Downloading GTFS Static data from NTA...")
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(API_BASE_URL_NTA_GTFS_STATIC, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to download GTFS Static: HTTP %s", response.status)
                    return False

                # Ensure cache directory exists
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)

                # Download to cache file
                async with aio_open(self._cache_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)

                _LOGGER.info("GTFS Static ZIP downloaded successfully")

                # Save timestamp
                async with aio_open(self._cache_timestamp_path, "w") as f:
                    await f.write(datetime.now().isoformat())

                # Load from cache
                return await self._load_from_cache()

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout downloading GTFS Static data")
            return False
        except Exception as e:
            _LOGGER.error("Error downloading GTFS Static data: %s", e, exc_info=True)
            return False

    async def _load_from_cache(self) -> bool:
        """Load GTFS Static data from cached ZIP file."""
        if not self._cache_path.exists():
            _LOGGER.error("GTFS Static cache file not found")
            return False

        try:
            # Read ZIP file
            async with aio_open(self._cache_path, "rb") as f:
                zip_data = await f.read()

            with zipfile.ZipFile(io.BytesIO(zip_data)) as zip_file:
                # Load stops.txt
                if "stops.txt" in zip_file.namelist():
                    with zip_file.open("stops.txt") as stops_file:
                        reader = csv.DictReader(io.TextIOWrapper(stops_file, encoding="utf-8"))
                        self.stops = {row["stop_id"]: row for row in reader}
                        _LOGGER.info("Loaded %d stops from GTFS Static", len(self.stops))

                # Load routes.txt
                if "routes.txt" in zip_file.namelist():
                    with zip_file.open("routes.txt") as routes_file:
                        reader = csv.DictReader(io.TextIOWrapper(routes_file, encoding="utf-8"))
                        self.routes = {row["route_id"]: row for row in reader}
                        _LOGGER.info("Loaded %d routes from GTFS Static", len(self.routes))

                # Load trips.txt
                if "trips.txt" in zip_file.namelist():
                    with zip_file.open("trips.txt") as trips_file:
                        reader = csv.DictReader(io.TextIOWrapper(trips_file, encoding="utf-8"))
                        self.trips = {row["trip_id"]: row for row in reader}
                        _LOGGER.info("Loaded %d trips from GTFS Static", len(self.trips))

                # Load stop_times.txt (optional, for future use)
                if "stop_times.txt" in zip_file.namelist():
                    with zip_file.open("stop_times.txt") as stop_times_file:
                        reader = csv.DictReader(io.TextIOWrapper(stop_times_file, encoding="utf-8"))
                        self.stop_times = {}
                        for row in reader:
                            trip_id = row["trip_id"]
                            if trip_id not in self.stop_times:
                                self.stop_times[trip_id] = []
                            self.stop_times[trip_id].append(row)
                        _LOGGER.info("Loaded stop_times for %d trips from GTFS Static", len(self.stop_times))

            self._last_update = datetime.now()
            return True

        except Exception as e:
            _LOGGER.error("Error loading GTFS Static from cache: %s", e, exc_info=True)
            return False

    def get_stop_name(self, stop_id: str) -> Optional[str]:
        """Get stop name by stop_id."""
        stop = self.stops.get(stop_id)
        if stop:
            return stop.get("stop_name")
        return None

    def get_route_short_name(self, route_id: str) -> Optional[str]:
        """Get route short name by route_id."""
        route = self.routes.get(route_id)
        if route:
            return route.get("route_short_name") or route.get("route_long_name")
        return None

    def get_route_type(self, route_id: str) -> Optional[int]:
        """Get route type by route_id."""
        route = self.routes.get(route_id)
        if route:
            try:
                return int(route.get("route_type", 3))  # Default to bus (3)
            except (ValueError, TypeError):
                return 3
        return None

    def search_stops(self, search_term: str, limit: int = 20) -> List[Dict[str, str]]:
        """Search stops by name (case-insensitive)."""
        search_term_lower = search_term.lower()
        results = []

        for stop_id, stop in self.stops.items():
            stop_name = stop.get("stop_name", "").lower()
            if search_term_lower in stop_name:
                results.append(
                    {
                        "stop_id": stop_id,
                        "stop_name": stop.get("stop_name", ""),
                        "stop_lat": stop.get("stop_lat", ""),
                        "stop_lon": stop.get("stop_lon", ""),
                    }
                )
                if len(results) >= limit:
                    break

        return results
