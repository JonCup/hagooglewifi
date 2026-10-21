"""Google Wifi API client with DHCP IP reservation support."""
import asyncio
import json

from googlewifi import GoogleWifi as _GoogleWifi
from googlewifi import GoogleWifiException

FOYER_URL = "https://googlehomefoyer-pa.googleapis.com/v2"


class GoogleWifi(_GoogleWifi):
    """The googlewifi client plus reading and writing lanSettings.staticIpMappings."""

    async def get_group(self, system_id: str):
        """Return the raw group (system) record."""
        if await self.connect():
            url = f"{FOYER_URL}/groups/{system_id}"
            headers = {
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json; charset=utf-8",
            }
            return await self.get_api(url, headers, {}, params=(("prettyPrint", "false"),))
        return {}

    async def get_static_ip_mappings(self, system_id: str):
        """Return the DHCP reservations as a list of {stationId, ipAddress}."""
        group = await self.get_group(system_id)
        lan = (group or {}).get("groupSettings", {}).get("lanSettings", {})
        return list(lan.get("staticIpMappings", []) or [])

    async def _write_lan_settings(self, system_id: str, lan_settings: dict):
        """Send the full lanSettings back to Google.

        Google has no published endpoint for this, so the known request shapes are
        tried in order. A 400/404/405 means that shape is not accepted and nothing changed.
        """
        attempts = (
            ("PUT", f"{FOYER_URL}/groups/{system_id}/lanSettings", (), lan_settings),
            (
                "PATCH",
                f"{FOYER_URL}/groups/{system_id}",
                (("updateMask", "groupSettings.lanSettings.staticIpMappings"),),
                {"groupSettings": {"lanSettings": lan_settings}},
            ),
        )
        errors = []
        for method, url, params, body in attempts:
            headers = {
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json; charset=utf-8",
            }
            async with self._session.request(
                method,
                url,
                headers=headers,
                params=(("prettyPrint", "false"),) + params,
                json=body,
                timeout=30,
            ) as resp:
                text = await resp.text()
                if resp.status < 400:
                    return method, json.loads(text) if text else {}
                errors.append(f"{method} {url.rsplit('/', 1)[-1]}: HTTP {resp.status} {text[:200]}")
                if resp.status not in (400, 404, 405):
                    break
        raise GoogleWifiException("Google rejected the reservation change: " + " | ".join(errors))

    async def set_static_ip_mappings(self, system_id: str, mappings: list):
        """Replace the DHCP reservations, then confirm Google stored exactly that list."""
        if not await self.connect():
            return False

        group = await self.get_group(system_id)
        lan_settings = dict(group.get("groupSettings", {}).get("lanSettings", {}))
        if not lan_settings.get("dhcpPoolBegin"):
            raise GoogleWifiException("Could not read the current LAN settings; nothing was changed.")
        lan_settings["staticIpMappings"] = mappings

        method, response = await self._write_lan_settings(system_id, lan_settings)

        operation_id = response.get("operation", {}).get("operationId")
        if operation_id:
            for _ in range(12):
                if (await self.check_operation(operation_id)).get("operationState") == "DONE":
                    break
                await asyncio.sleep(5)

        wanted = {(m["stationId"], m["ipAddress"]) for m in mappings}
        for _ in range(6):
            stored = {
                (m.get("stationId"), m.get("ipAddress"))
                for m in await self.get_static_ip_mappings(system_id)
            }
            if stored == wanted:
                return method
            await asyncio.sleep(5)
        raise GoogleWifiException(
            f"{method} was accepted but the reservations Google reports don't match what was sent."
        )
