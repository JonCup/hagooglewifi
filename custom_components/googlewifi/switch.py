"""Support for Google Wifi Connected Devices as Switch Internet on/off."""
import ipaddress
import logging
import time

import voluptuous as vol
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import ATTR_NAME, UnitOfDataRate
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util.dt import as_local, as_timestamp, parse_datetime

from . import GoogleWifiEntity, GoogleWiFiUpdater
from googlewifi import GoogleWifiException
from .const import (
    ATTR_CONNECTIONS,
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    CONF_SPEED_UNITS,
    COORDINATOR,
    DEFAULT_ICON,
    DEV_CLIENT_MODEL,
    DOMAIN,
    PAUSE_UPDATE,
    SIGNAL_ADD_DEVICE,
    unit_convert,
)

SERVICE_PRIORITIZE = "prioritize"
SERVICE_CLEAR_PRIORITIZATION = "prioritize_reset"
SERVICE_RESERVE_IP = "reserve_ip"
SERVICE_REMOVE_IP_RESERVATION = "remove_ip_reservation"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the switch platform."""

    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    device = hass.data[DOMAIN][entry.entry_id]

    entities = []

    data_unit = entry.options.get(CONF_SPEED_UNITS, UnitOfDataRate.MEGABITS_PER_SECOND)

    for system_id, system in coordinator.data.items():
        for dev_id, device in system["devices"].items():
            device_name = f"{device['friendlyName']}"

            if device.get("friendlyType"):
                device_name = device_name + f" ({device['friendlyType']})"

            entity = GoogleWifiSwitch(
                coordinator=coordinator,
                name=device_name,
                icon=DEFAULT_ICON,
                system_id=system_id,
                item_id=dev_id,
                data_unit=data_unit,
            )
            entities.append(entity)

    async_add_entities(entities)

    async def async_new_entities(device_info):
        """Add new entities when they connect to Google Wifi."""
        system_id = device_info["system_id"]
        device_id = device_info["device_id"]
        device = device_info["device"]

        device_name = f"{device['friendlyName']}"

        if device.get("friendlyType"):
            device_name = device_name + f" ({device['friendlyType']})"

        entity = GoogleWifiSwitch(
            coordinator=coordinator,
            name=device_name,
            icon=DEFAULT_ICON,
            system_id=system_id,
            item_id=device_id,
            data_unit=data_unit,
        )
        entities = [entity]
        async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_DEVICE, async_new_entities)
    )

    # register service for reset
    platform = entity_platform.current_platform.get()

    platform.async_register_entity_service(
        SERVICE_PRIORITIZE,
        {vol.Required("duration"): cv.positive_int},
        "async_prioritize_device",
    )

    platform.async_register_entity_service(
        SERVICE_CLEAR_PRIORITIZATION,
        {},
        "async_clear_prioritization",
    )

    platform.async_register_entity_service(
        SERVICE_RESERVE_IP,
        {vol.Required("ip_address"): cv.string},
        "async_reserve_ip",
    )

    platform.async_register_entity_service(
        SERVICE_REMOVE_IP_RESERVATION,
        {},
        "async_remove_ip_reservation",
    )

    return True


class GoogleWifiSwitch(GoogleWifiEntity, SwitchEntity):
    """Defines a Google WiFi switch."""

    def __init__(self, coordinator, name, icon, system_id, item_id, data_unit):
        """Initialize the switch."""
        super().__init__(
            coordinator=coordinator,
            name=name,
            icon=icon,
            system_id=system_id,
            item_id=item_id,
        )

        self._state = None
        self._available = None
        self._last_change = 0
        self._mac = None
        self._unit_of_measurement = data_unit

    @property
    def is_on(self):
        """Return the status of the internet for this device."""
        since_last = int(time.time()) - self._last_change

        if since_last > PAUSE_UPDATE:
            try:
                is_prioritized = False
                is_prioritized_end = "NA"

                if (
                    self.coordinator.data[self._system_id]["groupSettings"][
                        "lanSettings"
                    ]
                    .get("prioritizedStation")
                    .get("stationId")
                ):
                    if (
                        self.coordinator.data[self._system_id]["groupSettings"][
                            "lanSettings"
                        ]["prioritizedStation"]["stationId"]
                        == self._item_id
                    ):
                        end_time = self.coordinator.data[self._system_id][
                            "groupSettings"
                        ]["lanSettings"]["prioritizedStation"]["prioritizationEndTime"]
                        is_prioritized_end = as_local(
                            parse_datetime(end_time)
                        ).strftime("%d-%b-%y %I:%M %p")

                        if as_timestamp(parse_datetime(end_time)) > time.time():
                            is_prioritized = True

                self._attrs["prioritized"] = is_prioritized
                self._attrs["prioritized_end"] = is_prioritized_end

                if self.coordinator.data[self._system_id]["devices"][self._item_id][
                    "paused"
                ]:
                    self._state = False
                else:
                    self._state = True
            except TypeError:
                pass
            except KeyError:
                pass

        if self.coordinator.data:
            self._mac = self.coordinator.data[self._system_id]["devices"][
                self._item_id
            ].get("macAddress", None)

            self._attrs["mac"] = self._mac if self._mac else "NA"
            self._attrs["ip"] = self.coordinator.data[self._system_id]["devices"][
                self._item_id
            ].get("ipAddress", "NA")

            transmit_speed = float(
                self.coordinator.data[self._system_id]["devices"][self._item_id]
                .get("traffic", {})
                .get("transmitSpeedBps", 0)
            )

            receive_speed = float(
                self.coordinator.data[self._system_id]["devices"][self._item_id]
                .get("traffic", {})
                .get("receiveSpeedBps", 0)
            )

            self._attrs[
                f"transmit_speed_{self._unit_of_measurement.replace('/', 'p').replace(' ', '_').lower()}"
            ] = unit_convert(transmit_speed, self._unit_of_measurement)
            self._attrs[
                f"receive_speed_{self._unit_of_measurement.replace('/', 'p').replace(' ', '_').lower()}"
            ] = unit_convert(receive_speed, self._unit_of_measurement)

            self._attrs["network"] = self.coordinator.data[self._system_id]["devices"][
                self._item_id
            ]["network"]

            self._attrs["reserved_ip"] = "NA"
            for mapping in (
                self.coordinator.data[self._system_id]["groupSettings"]["lanSettings"].get(
                    "staticIpMappings"
                )
                or []
            ):
                if mapping.get("stationId") == self._item_id:
                    self._attrs["reserved_ip"] = mapping.get("ipAddress", "NA")

        return self._state

    @property
    def available(self):
        """Switch is not available if it is not connected."""
        try:
            if (
                self.coordinator.data[self._system_id]["devices"][self._item_id].get(
                    "connected"
                )
                == True
            ):
                self._available = True
            else:
                self._available = False
        except TypeError:
            pass
        except KeyError:
            pass

        return self._available

    @property
    def device_info(self):
        """Define the device as a device tracker system."""
        if self._mac:
            mac = {(CONNECTION_NETWORK_MAC, self._mac)}
        else:
            mac = {}

        device_info = {
            ATTR_IDENTIFIERS: {(DOMAIN, self._item_id)},
            ATTR_CONNECTIONS: mac,
            ATTR_NAME: self._name,
            ATTR_MANUFACTURER: "Google",
            ATTR_MODEL: DEV_CLIENT_MODEL,
        }

        via_device_id = self._via_device_id()
        if via_device_id:
            device_info["via_device_id"] = via_device_id

        return device_info

    async def async_turn_on(self, **kwargs):
        """Turn on (unpause) internet to the client."""
        self._state = True
        self._last_change = time.time()
        self.async_schedule_update_ha_state()
        await self.coordinator.api.pause_device(self._system_id, self._item_id, False)

    async def async_turn_off(self, **kwargs):
        """Turn on (pause) internet to the client."""
        self._state = False
        self._last_change = time.time()
        self.async_schedule_update_ha_state()
        await self.coordinator.api.pause_device(self._system_id, self._item_id, True)

    async def async_prioritize_device(self, duration):
        """Prioritize a device for (optional) x hours."""

        await self.coordinator.api.clear_prioritization(self._system_id)

        await self.coordinator.api.prioritize_device(
            self._system_id,
            self._item_id,
            duration,
        )

    async def async_clear_prioritization(self):
        """Clear previous prioritization."""

        await self.coordinator.api.clear_prioritization(self._system_id)

    async def async_reserve_ip(self, ip_address):
        """Reserve a LAN IP for this client (DHCP IP reservation)."""

        lan = self.coordinator.data[self._system_id]["groupSettings"]["lanSettings"]
        try:
            address = ipaddress.ip_address(ip_address.strip())
            network = ipaddress.ip_network(
                f"{lan['dhcpPoolBegin']}/{lan.get('netmask') or lan.get('prefixLength') or 24}",
                strict=False,
            )
        except (KeyError, ValueError) as error:
            raise HomeAssistantError(f"Invalid IP address {ip_address}: {error}") from error

        if address not in network or address in (
            network.network_address,
            network.broadcast_address,
        ):
            raise HomeAssistantError(f"{address} is not a usable address in {network}.")
        if str(address) in {
            value
            for key, value in lan.items()
            if isinstance(value, str) and key not in ("dhcpPoolBegin", "dhcpPoolEnd")
        }:
            raise HomeAssistantError(f"{address} is used by the router itself.")

        current = await self.coordinator.api.get_static_ip_mappings(self._system_id)
        for mapping in current:
            if (
                mapping.get("ipAddress") == str(address)
                and mapping.get("stationId") != self._item_id
            ):
                raise HomeAssistantError(
                    f"{address} is already reserved for another device."
                )

        _LOGGER.warning("Google Wifi reservations before change: %s", current)
        mappings = [m for m in current if m.get("stationId") != self._item_id]
        mappings.append({"stationId": self._item_id, "ipAddress": str(address)})
        await self._write_reservations(mappings)

    async def async_remove_ip_reservation(self):
        """Remove this client's DHCP IP reservation."""

        current = await self.coordinator.api.get_static_ip_mappings(self._system_id)
        mappings = [m for m in current if m.get("stationId") != self._item_id]
        if len(mappings) == len(current):
            return

        _LOGGER.warning("Google Wifi reservations before change: %s", current)
        await self._write_reservations(mappings)

    async def _write_reservations(self, mappings):
        """Write the full reservation list and refresh."""

        known = (
            self.coordinator.data[self._system_id]["groupSettings"]["lanSettings"].get(
                "staticIpMappings"
            )
            or []
        )
        kept = {m.get("stationId") for m in mappings}
        missing = [
            m
            for m in known
            if m.get("stationId") not in kept and m.get("stationId") != self._item_id
        ]
        if missing:
            raise HomeAssistantError(
                f"Refusing to write: {len(missing)} existing reservation(s) would be dropped; nothing was changed."
            )

        try:
            await self.coordinator.api.set_static_ip_mappings(self._system_id, mappings)
        except GoogleWifiException as error:
            raise HomeAssistantError(str(error)) from error
        await self.coordinator.async_request_refresh()
