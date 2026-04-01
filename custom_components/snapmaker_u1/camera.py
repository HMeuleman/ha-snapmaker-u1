"""Camera platform for the Snapmaker U1 integration (MJPEG webcam)."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SnapmakerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CAMERA_CONNECT_TIMEOUT = 5
CAMERA_READ_TIMEOUT = 10
# Refresh the still image every 1 seconds when the camera card is open
CAMERA_FRAME_INTERVAL = 1.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Snapmaker U1 cameras from a config entry."""
    coordinator: SnapmakerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SnapmakerCamera(hass, coordinator),
        SnapmakerPrintPreviewCamera(hass, coordinator),
    ])


class SnapmakerCamera(Camera):
    """Snapshot-based camera entity for the Snapmaker U1 webcam.

    Uses ``async_camera_image`` to fetch JPEG stills from the Moonraker
    snapshot endpoint.  ``stream_source`` is intentionally not implemented
    so that Home Assistant does not attempt HLS transcoding of the MJPEG
    stream (which requires ffmpeg and is often unnecessary for a printer cam).
    """

    _attr_has_entity_name = True
    _attr_name = "Webcam"
    _attr_supported_features = CameraEntityFeature(0)
    _attr_frame_interval = CAMERA_FRAME_INTERVAL

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SnapmakerDataUpdateCoordinator,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._hass = hass
        host = coordinator.entry.data["host"]
        self._attr_unique_id = f"{host}_webcam"
        self._client = coordinator.client

    @property
    def device_info(self) -> DeviceInfo:
        host = self._coordinator.entry.data["host"]
        return DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=self._coordinator.printer_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_streaming(self) -> bool:
        return self._coordinator.data.is_ready if self._coordinator.data else False

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a single JPEG snapshot from the webcam."""
        if self._client is None:
            return None
        snapshot_url = self._client.camera_snapshot_url
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                snapshot_url,
                timeout=aiohttp.ClientTimeout(
                    connect=CAMERA_CONNECT_TIMEOUT, total=CAMERA_READ_TIMEOUT
                ),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                _LOGGER.warning(
                    "Webcam snapshot returned HTTP %d from %s", resp.status, snapshot_url
                )
                return None
        except aiohttp.ClientError as exc:
            _LOGGER.debug("Webcam snapshot error: %s", exc)
            return None


class SnapmakerPrintPreviewCamera(Camera):
    """Snapshot-based camera entity for the Snapmaker U1 print preview.

    Fetches the thumbnail image of the currently printing G-code file.
    """

    _attr_has_entity_name = True
    _attr_name = "Print Preview"
    _attr_supported_features = CameraEntityFeature(0)
    _attr_frame_interval = CAMERA_FRAME_INTERVAL

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SnapmakerDataUpdateCoordinator,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._hass = hass
        host = coordinator.entry.data["host"]
        self._attr_unique_id = f"{host}_print_preview"
        self._client = coordinator.client

    @property
    def device_info(self) -> DeviceInfo:
        host = self._coordinator.entry.data["host"]
        return DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=self._coordinator.printer_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_streaming(self) -> bool:
        return self._coordinator.data.is_ready if self._coordinator.data else False

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the thumbnail image of the current print job."""
        if self._client is None:
            return None
        filename = self._coordinator.data.print_stats.filename
        if not filename:
            return None
        # Remove .gcode extension if present
        base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        thumbnail_url = f"{self._client.base_url}/server/files/gcodes/.thumbs/{base_name}-300x300.png"
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                thumbnail_url,
                timeout=aiohttp.ClientTimeout(
                    connect=CAMERA_CONNECT_TIMEOUT, total=CAMERA_READ_TIMEOUT
                ),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                _LOGGER.debug(
                    "Print preview thumbnail returned HTTP %d from %s", resp.status, thumbnail_url
                )
                return None
        except aiohttp.ClientError as exc:
            _LOGGER.debug("Print preview thumbnail error: %s", exc)
            return None
