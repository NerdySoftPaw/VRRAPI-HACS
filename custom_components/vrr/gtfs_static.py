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
        # trips and stop_times are not loaded to save memory (not currently used)
        self._cache_path = Path(hass.config.config_dir) / ".storage" / DOMAIN / "gtfs_static.zip"
        self._cache_timestamp_path = Path(hass.config.config_dir) / ".storage" / DOMAIN / "gtfs_static_timestamp.txt"
        self._last_update: Optional[datetime] = None

    async def ensure_loaded(self) -> bool:
        """Ensure GTFS Static data is loaded (download if needed)."""
        try:
            # Check if we need to download/update
            if await self._should_update():
                if not await self._download_and_load():
                    _LOGGER.error("Failed to download GTFS Static data")
                    return False

            # Load from cache if not already loaded
            if not self.stops and self._cache_path.exists():
                if not await self._load_from_cache():
                    _LOGGER.error("Failed to load GTFS Static data from cache")
                    return False

            if len(self.stops) == 0:
                _LOGGER.error("GTFS Static data is empty after loading")
                return False

            return True
        except Exception as e:
            _LOGGER.error("Error in ensure_loaded: %s", e, exc_info=True)
            return False

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
            # Ensure cache directory exists before downloading
            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                _LOGGER.debug("Cache directory: %s", self._cache_path.parent)
            except OSError as e:
                _LOGGER.error("Failed to create cache directory %s: %s", self._cache_path.parent, e)
                return False
            except Exception as e:
                _LOGGER.error("Unexpected error creating cache directory: %s", e)
                return False

            _LOGGER.info("Downloading GTFS Static from: %s", API_BASE_URL_NTA_GTFS_STATIC)
            async with session.get(API_BASE_URL_NTA_GTFS_STATIC, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to download GTFS Static: HTTP %s", response.status)
                    return False

                # Download to cache file in chunks to reduce memory usage
                total_size = 0
                async with aio_open(self._cache_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(65536):  # 64KB chunks
                        await f.write(chunk)
                        total_size += len(chunk)
                        # Log progress every 10MB
                        if total_size % (10 * 1024 * 1024) < 65536:
                            _LOGGER.debug("Downloaded %.2f MB...", total_size / 1024 / 1024)

                _LOGGER.info("GTFS Static ZIP downloaded successfully (%.2f MB)", total_size / 1024 / 1024)

                # Save timestamp
                async with aio_open(self._cache_timestamp_path, "w") as f:
                    await f.write(datetime.now().isoformat())

                # Load from cache
                return await self._load_from_cache()

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout downloading GTFS Static data (60s limit)")
            return False
        except aiohttp.ClientError as e:
            _LOGGER.error("Network error downloading GTFS Static data: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Unexpected error downloading GTFS Static data: %s", e, exc_info=True)
            return False

    async def _load_from_cache(self) -> bool:
        """Load GTFS Static data from cached ZIP file."""
        if not self._cache_path.exists():
            _LOGGER.error("GTFS Static cache file not found at: %s", self._cache_path)
            return False

        try:
            # Use ZipFile directly from file path to avoid loading entire file into memory
            _LOGGER.debug("Reading GTFS Static cache file: %s", self._cache_path)
            file_size = self._cache_path.stat().st_size
            _LOGGER.debug("GTFS Static ZIP file size: %d bytes (%.2f MB)", file_size, file_size / 1024 / 1024)

            # Open ZIP file directly from disk (more memory efficient)
            with zipfile.ZipFile(self._cache_path, "r") as zip_file:
                file_list = zip_file.namelist()
                _LOGGER.debug("GTFS Static ZIP contains %d files: %s", len(file_list), ", ".join(file_list[:10]))

                # Load stops.txt (required)
                if "stops.txt" not in file_list:
                    _LOGGER.error("stops.txt not found in GTFS Static ZIP")
                    return False

                # Load stops.txt in chunks to reduce memory usage
                with zip_file.open("stops.txt") as stops_file:
                    reader = csv.DictReader(io.TextIOWrapper(stops_file, encoding="utf-8"))
                    stop_count = 0
                    for row in reader:
                        self.stops[row["stop_id"]] = row
                        stop_count += 1
                        # Log progress every 10000 stops
                        if stop_count % 10000 == 0:
                            _LOGGER.debug("Loaded %d stops...", stop_count)
                    _LOGGER.info("Loaded %d stops from GTFS Static", stop_count)

                # Load routes.txt (optional but recommended) in chunks
                if "routes.txt" in file_list:
                    with zip_file.open("routes.txt") as routes_file:
                        reader = csv.DictReader(io.TextIOWrapper(routes_file, encoding="utf-8"))
                        route_count = 0
                        for row in reader:
                            self.routes[row["route_id"]] = row
                            route_count += 1
                        _LOGGER.info("Loaded %d routes from GTFS Static", route_count)
                else:
                    _LOGGER.warning("routes.txt not found in GTFS Static ZIP - route names will not be available")

                # Note: trips.txt and stop_times.txt are NOT loaded to save memory
                # They are not currently used and can be very large (millions of entries)

            if len(self.stops) == 0:
                _LOGGER.error("No stops loaded from GTFS Static - stops.txt may be empty or invalid")
                return False

            self._last_update = datetime.now()
            _LOGGER.info("Successfully loaded GTFS Static data: %d stops, %d routes", len(self.stops), len(self.routes))
            return True

        except zipfile.BadZipFile as e:
            _LOGGER.error("GTFS Static cache file is not a valid ZIP file: %s", e)
            # Try to delete corrupted cache
            try:
                self._cache_path.unlink()
            except Exception:
                pass
            return False
        except KeyError as e:
            _LOGGER.error("Missing required field in GTFS Static CSV: %s", e)
            return False
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
