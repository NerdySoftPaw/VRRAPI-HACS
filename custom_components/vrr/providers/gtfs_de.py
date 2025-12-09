"""GTFS-DE (Germany) provider implementation."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import ClientConnectorError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from ..const import API_BASE_URL_GTFS_DE_GTFSR, GTFS_DE_TRANSPORTATION_TYPES, PROVIDER_GTFS_DE
from ..data_models import UnifiedDeparture
from ..gtfs_static import GTFSStaticData
from ..parsers import parse_departure_generic
from .base import BaseProvider

_LOGGER = logging.getLogger(__name__)


class GTFSDEProvider(BaseProvider):
    """GTFS-DE (Germany) provider."""

    def __init__(self, hass, api_key: Optional[str] = None, api_key_secondary: Optional[str] = None):
        """Initialize GTFS-DE provider."""
        super().__init__(hass, api_key=api_key, api_key_secondary=api_key_secondary)
        self.gtfs_static: Optional[GTFSStaticData] = GTFSStaticData(hass, provider=PROVIDER_GTFS_DE)

    @property
    def provider_id(self) -> str:
        """Return the provider identifier."""
        return PROVIDER_GTFS_DE

    @property
    def provider_name(self) -> str:
        """Return the human-readable provider name."""
        return "GTFS-DE (Germany)"

    def get_timezone(self) -> str:
        """Return the timezone for GTFS-DE."""
        return "Europe/Berlin"

    async def fetch_departures(
        self,
        station_id: Optional[str],
        place_dm: str,
        name_dm: str,
        departures_limit: int,
    ) -> Optional[Dict[str, Any]]:
        """Fetch departure data from GTFS-DE GTFS-RT API (Protobuf format)."""
        if not station_id:
            _LOGGER.error("GTFS-DE requires a station ID (stop_id)")
            return None

        # Ensure GTFS Static data is loaded
        if self.gtfs_static and not await self.gtfs_static.ensure_loaded():
            _LOGGER.error("Failed to load GTFS Static data for GTFS-DE")
            return None

        try:
            from google.transit import gtfs_realtime_pb2
        except ImportError:
            _LOGGER.error("gtfs-realtime-bindings not installed. Please install it: pip install gtfs-realtime-bindings")
            return None

        url = API_BASE_URL_GTFS_DE_GTFSR
        session = async_get_clientsession(self.hass)

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant GTFS-DE Integration)",
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        try:
                            protobuf_data = await response.read()

                            feed_message = gtfs_realtime_pb2.FeedMessage()
                            feed_message.ParseFromString(protobuf_data)

                            entities = feed_message.entity
                            entity_count = len(entities)
                            if entity_count == 0:
                                _LOGGER.debug("GTFS-DE API returned empty entities list")
                                return {"stopEvents": []}

                            _LOGGER.info(
                                "GTFS-DE API returned %d entities (processing for stop %s)", entity_count, station_id
                            )

                            stop_events = []
                            target_stop_id = station_id
                            max_departures = departures_limit * 3
                            processed_entities = 0
                            max_entities_to_check = 100000 if entity_count > 50000 else entity_count

                            for idx, entity in enumerate(entities):
                                if idx >= max_entities_to_check and len(stop_events) > 0:
                                    _LOGGER.debug(
                                        "GTFS-DE: Early exit after checking %d entities, found %d departures",
                                        idx,
                                        len(stop_events),
                                    )
                                    break
                                if processed_entities >= max_departures:
                                    break

                                if not entity.HasField("trip_update"):
                                    continue

                                trip_update = entity.trip_update
                                stop_time_updates = trip_update.stop_time_update
                                if not stop_time_updates:
                                    continue

                                matching_stop_time = None
                                for stop_time_update in stop_time_updates:
                                    if stop_time_update.stop_id == target_stop_id:
                                        matching_stop_time = stop_time_update
                                        break

                                if matching_stop_time is None:
                                    continue

                                trip = trip_update.trip
                                route_id = trip.route_id
                                trip_id = trip.trip_id

                                route_short_name = ""
                                route_type = None
                                agency_name = None
                                platform_code = None
                                if self.gtfs_static:
                                    route_short_name = self.gtfs_static.get_route_short_name(route_id) or ""
                                    route_type = self.gtfs_static.get_route_type(route_id)
                                    agency_name = self.gtfs_static.get_agency_name(route_id)
                                    platform_code = self.gtfs_static.get_stop_platform_code(target_stop_id)

                                    if route_type is None:
                                        route_type = 3

                                delay_seconds = 0
                                if matching_stop_time.HasField("departure"):
                                    if matching_stop_time.departure.HasField("delay"):
                                        delay_seconds = matching_stop_time.departure.delay
                                elif matching_stop_time.HasField("arrival"):
                                    if matching_stop_time.arrival.HasField("delay"):
                                        delay_seconds = matching_stop_time.arrival.delay

                                schedule_relationship = matching_stop_time.schedule_relationship
                                if schedule_relationship == gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.CANCELED:
                                    continue

                                destination = "Unknown"
                                if self.gtfs_static:
                                    trip_headsign = self.gtfs_static.get_trip_headsign(trip_id)
                                    if trip_headsign:
                                        destination = trip_headsign
                                    else:
                                        route = self.gtfs_static.routes.get(route_id, {})
                                        destination = route.get("route_long_name") or route_short_name or "Unknown"

                                now = dt_util.now()

                                planned_time = now
                                estimated_time = now

                                if matching_stop_time.HasField("departure"):
                                    if matching_stop_time.departure.HasField("time"):
                                        try:
                                            planned_time = datetime.fromtimestamp(
                                                matching_stop_time.departure.time, tz=now.tzinfo
                                            )
                                            estimated_time = planned_time + timedelta(seconds=delay_seconds)
                                        except (ValueError, OSError):
                                            planned_time = now
                                            estimated_time = now + timedelta(seconds=delay_seconds)
                                elif matching_stop_time.HasField("arrival"):
                                    if matching_stop_time.arrival.HasField("time"):
                                        try:
                                            planned_time = datetime.fromtimestamp(
                                                matching_stop_time.arrival.time, tz=now.tzinfo
                                            )
                                            estimated_time = planned_time + timedelta(seconds=delay_seconds)
                                        except (ValueError, OSError):
                                            planned_time = now
                                            estimated_time = now + timedelta(seconds=delay_seconds)

                                planned_time_str = planned_time.strftime("%Y-%m-%dT%H:%M:%S%z")
                                estimated_time_str = estimated_time.strftime("%Y-%m-%dT%H:%M:%S%z")

                                platform = platform_code or ""
                                if matching_stop_time.HasField("departure"):
                                    if matching_stop_time.departure.HasField("platform"):
                                        platform = matching_stop_time.departure.platform.name or platform

                                stop_event = {
                                    "departureTimePlanned": planned_time_str,
                                    "departureTimeEstimated": estimated_time_str,
                                    "transportation": {
                                        "number": route_short_name,
                                        "description": agency_name or "",
                                        "destination": {"name": destination},
                                        "product": {"class": route_type or 3},
                                    },
                                    "platform": {"name": platform},
                                    "realtimeStatus": ["MONITORED"] if delay_seconds != 0 else [],
                                    "route_id": route_id,
                                    "trip_id": trip_id,
                                    "stop_id": target_stop_id,
                                    "delay_seconds": delay_seconds,
                                    "agency": agency_name,
                                }
                                stop_events.append(stop_event)
                                processed_entities += 1

                                if len(stop_events) >= max_departures:
                                    break

                            _LOGGER.info(
                                "GTFS-DE: Processed %d/%d entities, found %d departures for stop %s",
                                processed_entities,
                                entity_count,
                                len(stop_events),
                                target_stop_id,
                            )
                            return {"stopEvents": stop_events}

                        except Exception as e:
                            _LOGGER.warning("GTFS-DE Protobuf parsing failed: %s", e, exc_info=True)
                            return None
                    elif response.status == 404:
                        _LOGGER.warning("GTFS-DE API endpoint not found (404)")
                        return None
                    elif response.status >= 500:
                        _LOGGER.warning(
                            "GTFS-DE API server error (status %s) on attempt %d/%d",
                            response.status,
                            attempt,
                            max_retries,
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(2**attempt)
                            continue
                        return None
                    else:
                        _LOGGER.warning(
                            "GTFS-DE API returned status %s on attempt %d/%d",
                            response.status,
                            attempt,
                            max_retries,
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(2**attempt)
                            continue

            except asyncio.TimeoutError:
                _LOGGER.warning("GTFS-DE API timeout on attempt %d/%d", attempt, max_retries)
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
            except ClientConnectorError as e:
                _LOGGER.warning("GTFS-DE API connection error on attempt %d/%d: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
            except Exception as e:
                _LOGGER.warning("GTFS-DE API attempt %d/%d failed: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                    continue

        return None

    def parse_departure(
        self, stop: Dict[str, Any], tz: Union[ZoneInfo, Any], now: datetime
    ) -> Optional[UnifiedDeparture]:
        """Parse a single departure from GTFS-DE GTFS-RT API response."""
        transportation = stop.get("transportation", {})
        product = transportation.get("product", {})
        route_type = product.get("class", 3)
        transport_type = GTFS_DE_TRANSPORTATION_TYPES.get(route_type, "bus")

        return parse_departure_generic(
            stop,
            tz,
            now,
            get_transport_type_fn=lambda t: transport_type,
            get_platform_fn=lambda s: (
                s.get("platform", {}).get("name", "")
                if isinstance(s.get("platform"), dict)
                else str(s.get("platform", ""))
            ),
            get_realtime_fn=lambda s, est, plan: "MONITORED" in s.get("realtimeStatus", []),
        )

    async def search_stops(self, search_term: str) -> List[Dict[str, Any]]:
        """Search for stops using GTFS Static data."""
        if not self.gtfs_static:
            self.gtfs_static = GTFSStaticData(self.hass, provider=PROVIDER_GTFS_DE)

        if not await self.gtfs_static.ensure_loaded():
            _LOGGER.error("Failed to load GTFS Static data for GTFS-DE stop search")
            return []

        results = self.gtfs_static.search_stops(search_term, limit=20)

        stops = []
        for result in results:
            stop_name = result.get("stop_name", "")
            place = ""
            if "," in stop_name:
                parts = stop_name.split(",")
                place = parts[-1].strip() if len(parts) > 1 else ""
                stop_name = ",".join(parts[:-1]).strip()

            stops.append(
                {
                    "id": result.get("stop_id", ""),
                    "name": stop_name,
                    "place": place,
                }
            )

        return stops
