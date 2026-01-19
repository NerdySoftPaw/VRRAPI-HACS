"""GTFS Static data loader for NTA Ireland and GTFS-DE Germany."""

import asyncio
import csv
import io
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import aiohttp
from aiofiles import open as aio_open
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL_GTFS_DE_GTFS_STATIC,
    API_BASE_URL_NTA_GTFS_STATIC,
    DOMAIN,
    PROVIDER_GTFS_DE,
    PROVIDER_NTA_IE,
)

if TYPE_CHECKING:
    from .gtfs_manager import GTFSManager

_LOGGER = logging.getLogger(__name__)

# Cache GTFS Static data for 24 hours
GTFS_CACHE_DURATION = timedelta(hours=24)


class GTFSStaticData:
    """Class to manage GTFS Static data loading and caching."""

    def __init__(
        self,
        hass: HomeAssistant,
        provider: str = PROVIDER_NTA_IE,
        manager: Optional["GTFSManager"] = None,
    ):
        """Initialize GTFS Static data loader.

        Args:
            hass: Home Assistant instance
            provider: Provider identifier (e.g., "nta_ie", "gtfs_de")
            manager: Optional GTFSManager reference for coordinated shutdown
        """
        self.hass = hass
        self.provider = provider
        self._manager = manager
        self.stops: Dict[str, Dict[str, str]] = {}  # stop_id -> stop data
        self.routes: Dict[str, Dict[str, str]] = {}  # route_id -> route data
        self.trips: Dict[str, str] = {}  # trip_id -> trip_headsign (only headsign loaded to save memory)
        self.agencies: Dict[str, Dict[str, str]] = {}  # agency_id -> agency data
        # Use provider-specific cache files
        cache_filename = f"gtfs_static_{provider}.zip"
        timestamp_filename = f"gtfs_static_{provider}_timestamp.txt"
        self._cache_path = Path(hass.config.config_dir) / ".storage" / DOMAIN / cache_filename
        self._cache_timestamp_path = Path(hass.config.config_dir) / ".storage" / DOMAIN / timestamp_filename
        self._last_update: Optional[datetime] = None
        # Lock to prevent concurrent downloads
        self._download_lock = asyncio.Lock()
        self._is_loading = False

    async def ensure_loaded(self) -> bool:
        """Ensure GTFS Static data is loaded (download if needed)."""
        # Check if manager is shutting down
        if self._manager and self._manager.is_shutting_down():
            _LOGGER.warning("GTFSManager is shutting down, skipping ensure_loaded")
            return False

        try:
            async with self._download_lock:
                # Check again after acquiring lock (manager might have started shutdown)
                if self._manager and self._manager.is_shutting_down():
                    return False

                # If already loaded, return immediately
                if self.stops:
                    return True

                self._is_loading = True
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
                finally:
                    self._is_loading = False
        except Exception as e:
            _LOGGER.error("Error in ensure_loaded: %s", e, exc_info=True)
            return False

    async def force_update(self) -> bool:
        """Force update GTFS Static data (download even if cache is recent)."""
        # Check if manager is shutting down
        if self._manager and self._manager.is_shutting_down():
            _LOGGER.warning("GTFSManager is shutting down, skipping force_update")
            return False

        _LOGGER.info("Forcing update of GTFS Static data for provider: %s", self.provider)
        try:
            async with self._download_lock:
                self._is_loading = True
                try:
                    # Force download and load
                    if not await self._download_and_load():
                        _LOGGER.error("Failed to force update GTFS Static data")
                        return False

                    if len(self.stops) == 0:
                        _LOGGER.error("GTFS Static data is empty after force update")
                        return False

                    _LOGGER.info("Successfully force updated GTFS Static data for provider: %s", self.provider)
                    return True
                finally:
                    self._is_loading = False
        except Exception as e:
            _LOGGER.error("Error in force_update: %s", e, exc_info=True)
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
        # Determine URL based on provider
        if self.provider == PROVIDER_NTA_IE:
            url = API_BASE_URL_NTA_GTFS_STATIC
            provider_name = "NTA"
        elif self.provider == PROVIDER_GTFS_DE:
            url = API_BASE_URL_GTFS_DE_GTFS_STATIC
            provider_name = "GTFS-DE"
        else:
            _LOGGER.error("Unknown provider for GTFS Static: %s", self.provider)
            return False

        _LOGGER.info("Downloading GTFS Static data from %s...", provider_name)
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

            _LOGGER.info("Downloading GTFS Static from: %s", url)
            # For GTFS-DE (large files), use longer timeout and larger chunks
            timeout_seconds = 600 if self.provider == PROVIDER_GTFS_DE else 300  # 10 min for GTFS-DE
            chunk_size = 262144 if self.provider == PROVIDER_GTFS_DE else 65536  # 256KB for GTFS-DE, 64KB otherwise

            # Set User-Agent header to avoid being blocked by some servers
            headers = {"User-Agent": "HomeAssistant-VRR-Integration/1.0"}

            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_seconds)
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to download GTFS Static: HTTP %s", response.status)
                    # Try to read error response body for debugging
                    try:
                        error_body = await response.text()
                        if len(error_body) < 500:  # Only log if reasonable size
                            _LOGGER.debug("Error response body: %s", error_body[:200])
                    except Exception:
                        pass
                    return False

                # Check Content-Type to ensure we're getting a ZIP file
                content_type = response.headers.get("Content-Type", "").lower()
                if content_type and "zip" not in content_type and "octet-stream" not in content_type:
                    _LOGGER.warning(
                        "Unexpected Content-Type for GTFS Static download: %s (expected application/zip or application/octet-stream)",
                        content_type,
                    )
                    # Don't fail here, as some servers may not set Content-Type correctly

                # Download to cache file in chunks to reduce memory usage
                total_size = 0
                try:
                    async with aio_open(self._cache_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            await f.write(chunk)
                            total_size += len(chunk)
                            # Log progress every 50MB for large files, 10MB for smaller
                            log_interval = 50 * 1024 * 1024 if self.provider == PROVIDER_GTFS_DE else 10 * 1024 * 1024
                            if total_size % log_interval < chunk_size:
                                _LOGGER.info("Downloaded %.2f MB...", total_size / 1024 / 1024)

                    # Verify file was written successfully
                    if total_size == 0:
                        _LOGGER.error("Downloaded file is empty")
                        try:
                            if self._cache_path.exists():
                                self._cache_path.unlink()
                        except Exception:
                            pass
                        return False

                    _LOGGER.info("GTFS Static ZIP downloaded successfully (%.2f MB)", total_size / 1024 / 1024)

                    # Save timestamp
                    async with aio_open(self._cache_timestamp_path, "w") as f:
                        await f.write(datetime.now().isoformat())

                    # Load from cache
                    _LOGGER.info("Attempting to load GTFS Static data from downloaded file...")
                    load_result = await self._load_from_cache()
                    if not load_result:
                        # If loading failed, delete the corrupted file
                        _LOGGER.error(
                            "Failed to load downloaded GTFS Static file. "
                            "The file may be corrupted or in an unexpected format. "
                            "Will retry on next attempt."
                        )
                        try:
                            if self._cache_path.exists():
                                file_size = self._cache_path.stat().st_size
                                _LOGGER.debug(
                                    "Deleting corrupted file (size: %d bytes, %.2f MB)",
                                    file_size,
                                    file_size / 1024 / 1024,
                                )
                                self._cache_path.unlink()
                            if self._cache_timestamp_path.exists():
                                self._cache_timestamp_path.unlink()
                        except Exception as del_e:
                            _LOGGER.warning("Failed to delete corrupted files: %s", del_e)
                    else:
                        _LOGGER.info("Successfully loaded GTFS Static data from downloaded file")
                    return load_result
                except Exception as write_error:
                    _LOGGER.error("Error writing GTFS Static file: %s", write_error, exc_info=True)
                    # Clean up partial file
                    try:
                        if self._cache_path.exists():
                            self._cache_path.unlink()
                    except Exception:
                        pass
                    return False

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout downloading GTFS Static data")
            # Clean up any partial download
            try:
                if self._cache_path.exists():
                    self._cache_path.unlink()
                    _LOGGER.info("Deleted partial/incomplete download")
            except Exception:
                pass
            return False
        except aiohttp.ClientError as e:
            _LOGGER.error("Network error downloading GTFS Static data: %s", e)
            # Clean up any partial download
            try:
                if self._cache_path.exists():
                    self._cache_path.unlink()
                    _LOGGER.info("Deleted partial/incomplete download")
            except Exception:
                pass
            return False
        except Exception as e:
            _LOGGER.error("Unexpected error downloading GTFS Static data: %s", e, exc_info=True)
            # Clean up any partial download
            try:
                if self._cache_path.exists():
                    self._cache_path.unlink()
                    _LOGGER.info("Deleted partial/incomplete download")
            except Exception:
                pass
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

            # Check if file is too small to be a valid ZIP (likely corrupted or incomplete download)
            if file_size < 1000:  # Less than 1KB is definitely not a valid GTFS ZIP
                _LOGGER.error(
                    "GTFS Static cache file is too small (%d bytes) - likely corrupted or incomplete", file_size
                )
                try:
                    self._cache_path.unlink()
                    _LOGGER.info("Deleted corrupted cache file, will re-download on next attempt")
                except Exception as e:
                    _LOGGER.warning("Failed to delete corrupted cache file: %s", e)
                return False

            # Check if file is actually a ZIP file by reading the magic bytes (async)
            try:
                async with aio_open(self._cache_path, "rb") as f:
                    magic_bytes = await f.read(4)
                    # ZIP files start with PK\x03\x04 or PK\x05\x06 (empty ZIP) or PK\x07\x08 (spanned ZIP)
                    if not magic_bytes.startswith(b"PK"):
                        _LOGGER.error(
                            "GTFS Static cache file does not appear to be a ZIP file "
                            "(magic bytes: %s). It may be an HTML error page or corrupted download.",
                            magic_bytes.hex() if len(magic_bytes) == 4 else "too short",
                        )
                        # Check if it's an HTML page
                        await f.seek(0)
                        first_bytes = await f.read(512)
                        if b"<html" in first_bytes.lower() or b"<!doctype" in first_bytes.lower():
                            _LOGGER.error(
                                "Downloaded file appears to be an HTML page, not a ZIP file. URL may be incorrect."
                            )
                        try:
                            self._cache_path.unlink()
                            _LOGGER.info("Deleted invalid cache file, will re-download on next attempt")
                        except Exception as e:
                            _LOGGER.warning("Failed to delete invalid cache file: %s", e)
                        return False
            except Exception as e:
                _LOGGER.warning("Could not verify ZIP file magic bytes: %s", e)

            # Run blocking ZIP file operations in a thread pool to avoid blocking the event loop
            result = await asyncio.to_thread(self._load_zip_contents_sync)
            return result

        except Exception as e:
            _LOGGER.error("Error loading GTFS Static from cache: %s", e, exc_info=True)
            return False

    def _load_zip_contents_sync(self) -> bool:
        """Load ZIP file contents synchronously (runs in thread pool)."""
        try:
            with zipfile.ZipFile(self._cache_path, "r") as zip_file:
                file_list = zip_file.namelist()
                _LOGGER.debug("GTFS Static ZIP contains %d files: %s", len(file_list), ", ".join(file_list[:10]))

                # Load stops.txt (required)
                if "stops.txt" not in file_list:
                    _LOGGER.error("stops.txt not found in GTFS Static ZIP")
                    return False

                # Load stops.txt in chunks to reduce memory usage
                # For large files (GTFS-DE), only store essential fields to save memory
                try:
                    with zip_file.open("stops.txt") as stops_file:
                        # Try UTF-8 first, fallback to latin-1 if needed
                        try:
                            reader = csv.DictReader(io.TextIOWrapper(stops_file, encoding="utf-8"))
                        except UnicodeDecodeError:
                            _LOGGER.warning("UTF-8 decoding failed for stops.txt, trying latin-1")
                            stops_file.seek(0)
                            reader = csv.DictReader(io.TextIOWrapper(stops_file, encoding="latin-1"))

                        stop_count = 0
                        for row in reader:
                            # Validate required field
                            if "stop_id" not in row:
                                _LOGGER.error("stops.txt missing required field 'stop_id'")
                                return False

                            # For GTFS-DE, only store essential fields to reduce memory usage
                            if self.provider == PROVIDER_GTFS_DE:
                                # Only store essential fields: stop_id, stop_name, stop_lat, stop_lon, platform_code
                                essential_fields = {
                                    "stop_id": row.get("stop_id", ""),
                                    "stop_name": row.get("stop_name", ""),
                                    "stop_lat": row.get("stop_lat", ""),
                                    "stop_lon": row.get("stop_lon", ""),
                                    "platform_code": row.get("platform_code", ""),
                                }
                                self.stops[row["stop_id"]] = essential_fields
                            else:
                                # For smaller files (NTA), store all fields
                                self.stops[row["stop_id"]] = row
                            stop_count += 1
                            # Log progress every 50000 stops for large files, 10000 for smaller
                            log_interval = 50000 if self.provider == PROVIDER_GTFS_DE else 10000
                            if stop_count % log_interval == 0:
                                _LOGGER.info("Loaded %d stops...", stop_count)
                        _LOGGER.info("Loaded %d stops from GTFS Static", stop_count)
                except Exception as e:
                    _LOGGER.error("Error reading stops.txt: %s", e, exc_info=True)
                    return False

                # Load routes.txt (optional but recommended) in chunks
                if "routes.txt" in file_list:
                    with zip_file.open("routes.txt") as routes_file:
                        reader = csv.DictReader(io.TextIOWrapper(routes_file, encoding="utf-8"))
                        route_count = 0
                        for row in reader:
                            # For GTFS-DE, only store essential fields to reduce memory usage
                            if self.provider == PROVIDER_GTFS_DE:
                                essential_fields = {
                                    "route_id": row.get("route_id", ""),
                                    "route_short_name": row.get("route_short_name", ""),
                                    "route_long_name": row.get("route_long_name", ""),
                                    "route_type": row.get("route_type", ""),
                                    "agency_id": row.get("agency_id", ""),
                                }
                                self.routes[row["route_id"]] = essential_fields
                            else:
                                self.routes[row["route_id"]] = row
                            route_count += 1
                            # Log progress every 10000 routes for large files
                            if self.provider == PROVIDER_GTFS_DE and route_count % 10000 == 0:
                                _LOGGER.info("Loaded %d routes...", route_count)
                        _LOGGER.info("Loaded %d routes from GTFS Static", route_count)
                else:
                    _LOGGER.warning("routes.txt not found in GTFS Static ZIP - route names will not be available")

                # Load trips.txt (only trip_headsign for destination, to save memory)
                if "trips.txt" in file_list:
                    with zip_file.open("trips.txt") as trips_file:
                        reader = csv.DictReader(io.TextIOWrapper(trips_file, encoding="utf-8"))
                        trip_count = 0
                        for row in reader:
                            trip_id = row.get("trip_id", "")
                            trip_headsign = row.get("trip_headsign", "")
                            if trip_id and trip_headsign:
                                self.trips[trip_id] = trip_headsign
                                trip_count += 1
                        _LOGGER.info("Loaded %d trip headsigns from GTFS Static", trip_count)
                else:
                    _LOGGER.warning("trips.txt not found in GTFS Static ZIP - destinations will not be available")

                # Load agency.txt (for operator information)
                if "agency.txt" in file_list:
                    with zip_file.open("agency.txt") as agency_file:
                        reader = csv.DictReader(io.TextIOWrapper(agency_file, encoding="utf-8"))
                        agency_count = 0
                        for row in reader:
                            agency_id = row.get("agency_id", "")
                            # If no agency_id, use agency_name as key (some GTFS feeds don't have agency_id)
                            if not agency_id:
                                agency_id = row.get("agency_name", "")
                            if agency_id:
                                self.agencies[agency_id] = row
                                agency_count += 1
                        _LOGGER.info("Loaded %d agencies from GTFS Static", agency_count)
                else:
                    _LOGGER.warning("agency.txt not found in GTFS Static ZIP - agency info will not be available")

                # Note: stop_times.txt is NOT loaded to save memory (can be millions of entries)

            if len(self.stops) == 0:
                _LOGGER.error("No stops loaded from GTFS Static - stops.txt may be empty or invalid")
                return False

            self._last_update = datetime.now()
            # Log memory-efficient summary
            memory_info = ""
            if self.provider == PROVIDER_GTFS_DE:
                # Estimate memory usage (rough calculation)
                stops_mem = len(self.stops) * 200  # ~200 bytes per stop (essential fields only)
                routes_mem = len(self.routes) * 150  # ~150 bytes per route
                trips_mem = len(self.trips) * 50  # ~50 bytes per trip (only headsign)
                agencies_mem = len(self.agencies) * 100  # ~100 bytes per agency
                total_mem_mb = (stops_mem + routes_mem + trips_mem + agencies_mem) / 1024 / 1024
                memory_info = f" (estimated memory: ~{total_mem_mb:.1f} MB)"
            _LOGGER.info(
                "Successfully loaded GTFS Static data: %d stops, %d routes, %d trips, %d agencies%s",
                len(self.stops),
                len(self.routes),
                len(self.trips),
                len(self.agencies),
                memory_info,
            )
            return True

        except zipfile.BadZipFile as e:
            _LOGGER.error("GTFS Static cache file is not a valid ZIP file: %s", e)
            # Try to delete corrupted cache and timestamp
            try:
                self._cache_path.unlink()
                _LOGGER.info("Deleted corrupted GTFS Static cache file")
            except Exception as del_e:
                _LOGGER.warning("Failed to delete corrupted cache file: %s", del_e)
            try:
                if self._cache_timestamp_path.exists():
                    self._cache_timestamp_path.unlink()
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
                route_type_str = route.get("route_type", "")
                if route_type_str:
                    route_type = int(route_type_str)
                    _LOGGER.debug("GTFS Static: route_id=%s, route_type=%d", route_id, route_type)
                    return route_type
                else:
                    _LOGGER.warning("GTFS Static: route_type missing for route_id=%s", route_id)
                    return None
            except (ValueError, TypeError) as e:
                _LOGGER.warning("GTFS Static: Invalid route_type for route_id=%s: %s", route_id, e)
                return None
        else:
            _LOGGER.debug("GTFS Static: route_id=%s not found in routes", route_id)
        return None

    def get_trip_headsign(self, trip_id: str) -> Optional[str]:
        """Get trip headsign (destination) by trip_id."""
        return self.trips.get(trip_id)

    def get_agency_name(self, route_id: str) -> Optional[str]:
        """Get agency name for a route_id."""
        route = self.routes.get(route_id)
        if not route:
            return None

        # Get agency_id from route
        agency_id = route.get("agency_id", "")
        if not agency_id:
            # Some GTFS feeds don't have agency_id in routes.txt
            # Try to get first agency if only one exists
            if len(self.agencies) == 1:
                agency = next(iter(self.agencies.values()))
                return agency.get("agency_name")
            return None

        # Get agency by agency_id
        agency = self.agencies.get(agency_id)
        if agency:
            return agency.get("agency_name")
        return None

    def get_stop_platform_code(self, stop_id: str) -> Optional[str]:
        """Get platform code for a stop_id from GTFS Static stops.txt."""
        stop = self.stops.get(stop_id)
        if not stop:
            return None
        # GTFS Static stops.txt can have platform_code field
        platform_code = stop.get("platform_code", "")
        return platform_code if platform_code else None

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

    async def clear_data(self) -> None:
        """Clear all loaded GTFS data to free memory.

        This method should be called during cleanup to release memory
        used by stops, routes, trips, and agencies dictionaries.
        """
        stops_count = len(self.stops)
        routes_count = len(self.routes)
        trips_count = len(self.trips)
        agencies_count = len(self.agencies)

        # Clear all data dictionaries
        self.stops.clear()
        self.routes.clear()
        self.trips.clear()
        self.agencies.clear()

        self._last_update = None
        self._is_loading = False

        _LOGGER.info(
            "Cleared GTFS Static data for %s: %d stops, %d routes, %d trips, %d agencies",
            self.provider,
            stops_count,
            routes_count,
            trips_count,
            agencies_count,
        )

    def get_stats(self) -> Dict[str, any]:
        """Get statistics about loaded GTFS data.

        Returns:
            Dictionary with data statistics
        """
        return {
            "provider": self.provider,
            "stops_count": len(self.stops),
            "routes_count": len(self.routes),
            "trips_count": len(self.trips),
            "agencies_count": len(self.agencies),
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "is_loading": self._is_loading,
            "cache_path": str(self._cache_path),
        }
