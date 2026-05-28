import asyncio
import datetime
import json
import time

import aiohttp
import dateutil.parser
import gpsoauth
import grpc
from ghome_foyer_api.api_pb2 import GetHomeGraphRequest
from ghome_foyer_api.api_pb2_grpc import StructuresServiceStub

GH_HEADERS = {"Content-Type": "application/json"}

GPS_SERVICE = "oauth2:https://www.google.com/accounts/OAuthLogin"
GPS_APP = "com.google.android.apps.chromecast.app"
GPS_CLIENT_SIG = "24bb24c05e47e0aefa68a58a766179d9b613a600"


class GoogleWifi:
    def __init__(self, refresh_token, session: aiohttp.ClientSession = None):
        self._session = session if session else aiohttp.ClientSession()
        self._refresh_token = refresh_token.strip()
        self._access_token = None
        self._api_token = None
        self._api_token_expires_at = 0
        self._systems = None
        self._access_points = {}

        self._auth_mode = "gps" if self._refresh_token.startswith("gps:") else "legacy"
        self._gps_email = None
        self._gps_android_id = None
        self._gps_master_token = None

        if self._auth_mode == "gps":
            parts = self._refresh_token.split(":", 3)
            if len(parts) != 4 or not parts[1] or not parts[2] or not parts[3]:
                raise ValueError("Invalid gps token bundle. Expected gps:email:android_id:master_token")
            _, self._gps_email, self._gps_android_id, self._gps_master_token = parts

    async def post_api(self, url: str, headers: dict = None, payload=None, params=None, json_payload=None):
        try:
            async with self._session.post(
                url,
                headers=headers,
                data=payload,
                params=params,
                verify_ssl=False,
                json=json_payload,
                timeout=30,
            ) as resp:
                response_text = await resp.text()
                if resp.status >= 400:
                    raise ConnectionError(f"POST {url} failed HTTP {resp.status}: {response_text[:500]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise ConnectionError(error) from error

        if response_text:
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as error:
                raise ValueError(error) from error
        return {}

    async def get_api(self, url: str, headers: dict = None, payload=None, params=None):
        try:
            async with self._session.get(
                url,
                headers=headers,
                data=payload,
                params=params,
                verify_ssl=False,
                timeout=30,
            ) as resp:
                response_text = await resp.text()
                if resp.status >= 400:
                    raise ConnectionError(f"GET {url} failed HTTP {resp.status}: {response_text[:500]}")
        except asyncio.TimeoutError as error:
            raise GoogleHomeIgnoreDevice(error) from error
        except aiohttp.ClientError as error:
            raise ConnectionError(error) from error

        if response_text:
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as error:
                raise ValueError(error) from error
        return {}

    async def put_api(self, url: str, headers: dict = None, payload=None, params=None):
        try:
            async with self._session.put(
                url,
                headers=headers,
                data=payload,
                params=params,
                verify_ssl=False,
                timeout=30,
            ) as resp:
                response_text = await resp.text()
                if resp.status >= 400:
                    raise ConnectionError(f"PUT {url} failed HTTP {resp.status}: {response_text[:500]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise ConnectionError(error) from error

        if response_text:
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as error:
                raise ValueError(error) from error
        return {}

    async def delete_api(self, url: str, headers: dict = None, payload=None, params=None):
        try:
            async with self._session.delete(
                url,
                headers=headers,
                data=payload,
                params=params,
                verify_ssl=False,
                timeout=30,
            ) as resp:
                response_text = await resp.text()
                if resp.status >= 400:
                    raise ConnectionError(f"DELETE {url} failed HTTP {resp.status}: {response_text[:500]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise ConnectionError(error) from error

        if response_text:
            try:
                return json.loads(response_text)
            except json.JSONDecodeError as error:
                raise ValueError(error) from error
        return {}

    async def get_access_token(self):
        if self._auth_mode != "gps":
            raise ConnectionError(
                "Legacy Google Wifi refresh-token flow is no longer supported by this patched build. "
                "Use gps:email:android_id:master_token."
            )

        def do_oauth():
            return gpsoauth.perform_oauth(
                self._gps_email,
                self._gps_master_token,
                self._gps_android_id,
                service=GPS_SERVICE,
                app=GPS_APP,
                client_sig=GPS_CLIENT_SIG,
            )

        response = await asyncio.to_thread(do_oauth)
        token = response.get("Auth")
        if not token:
            raise ConnectionError(f"gpsoauth did not return Auth. Keys: {sorted(response.keys())}")

        expires = int(response.get("ExpiresInDurationSec", 3600))
        self._access_token = token
        self._api_token = token
        self._api_token_expires_at = time.time() + max(60, expires - 300)
        return True

    async def get_api_token(self):
        if self._api_token and time.time() < self._api_token_expires_at:
            return True
        return await self.get_access_token()

    async def connect(self):
        return await self.get_api_token()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def get_systems(self):
        if await self.connect():
            url = "https://googlehomefoyer-pa.googleapis.com/v2/groups?prettyPrint=false"
            response = await self.get_api(url, self._headers(), {})
            if response.get("groups"):
                return await self.structure_systems(response)
            raise GoogleWifiException("Failed to retrieve Google Wifi data.")

    async def get_devices(self, system_id):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/stations?prettyPrint=false"
            return await self.get_api(url, self._headers(), {})

    async def get_status(self, system_id):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/status?prettyPrint=false"
            return await self.get_api(url, self._headers(), {})

    async def get_realtime_metrics(self, system_id):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/realtimeMetrics"
            return await self.get_api(url, self._headers(), {}, params=(("prettyPrint", "false"),))

    async def structure_systems(self, system_data):
        systems = {}

        for this_system in system_data["groups"]:
            system_id = this_system["id"]
            systems[system_id] = this_system

            system_status = await self.get_status(system_id)
            system_metrics = await self.get_realtime_metrics(system_id)

            systems[system_id]["status"] = system_status.get("wanConnectionStatus")
            systems[system_id]["groupTraffic"] = system_metrics.get("groupTraffic")

            family_settings = (
                this_system.get("groupSettings", {})
                .get("familyHubSettings", {})
                or {}
            )

            blocking_policies = {}
            for policy in family_settings.get("stationPolicies", []) or []:
                station_id = policy.get("stationId")
                if station_id:
                    blocking_policies[station_id] = policy

            ap_status = {}
            for this_ap in system_status.get("apStatuses", []) or []:
                if this_ap.get("apId"):
                    ap_status[this_ap["apId"]] = this_ap

            access_points = {}
            for this_ap in this_system.get("accessPoints", []) or []:
                ap_id = this_ap.get("id")
                if not ap_id:
                    continue
                access_points[ap_id] = this_ap
                access_points[ap_id]["status"] = ap_status.get(ap_id, {}).get("apState", "UNKNOWN")

            systems[system_id]["access_points"] = access_points

            devices_list = await self.get_devices(system_id)
            devices = {}
            station_ids = []

            for this_device in devices_list.get("stations", []) or []:
                device_id = this_device.get("id")
                if not device_id:
                    continue

                devices[device_id] = this_device
                station_ids.append(device_id)
                device_paused = False

                if blocking_policies.get(device_id):
                    expiry = (
                        blocking_policies[device_id]
                        .get("blockingPolicy", {})
                        .get("expiryTimestamp")
                    )
                    if expiry:
                        expire_date = dateutil.parser.parse(expiry)
                        if expire_date > datetime.datetime.now(datetime.timezone.utc) or expire_date.timestamp() == 0:
                            device_paused = True

                devices[device_id]["paused"] = device_paused

            sensitive_info = await self.get_sensitive_info(system_id=system_id, station_ids=station_ids)
            for station in sensitive_info:
                station_id = station.get("stationId")
                if station_id in devices:
                    devices[station_id]["macAddress"] = station.get("macAddress")

            for station_metric in system_metrics.get("stationMetrics", []) or []:
                station_id = station_metric.get("station", {}).get("id")
                if station_id in devices:
                    devices[station_id]["traffic"] = station_metric.get("traffic", {})

            systems[system_id]["devices"] = devices

        return systems

    async def pause_device(self, system_id: str, device_id: str, pause_state: bool):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/stationBlocking?prettyPrint=false"
            payload = json.dumps({"blocked": str(pause_state).lower(), "stationId": device_id})
            response = await self.put_api(url, headers=self._headers(), payload=payload)
            return response.get("operation", {}).get("operationState") == "CREATED"
        return False

    async def prioritize_device(self, system_id: str, device_id: str, duration_hours: int = 1):
        if await self.connect():
            duration_hours = max(1, min(6, duration_hours))
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/prioritizedStation?prettyPrint=false"
            end_time = datetime.datetime.now() + datetime.timedelta(hours=duration_hours)
            end_time = end_time.astimezone().replace(microsecond=0).isoformat()
            payload = json.dumps({"stationId": device_id, "prioritizationEndTime": end_time})
            response = await self.put_api(url, headers=self._headers(), payload=payload)
            return response.get("operation", {}).get("operationState") == "CREATED"
        return False

    async def clear_prioritization(self, system_id: str):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/prioritizedStation?prettyPrint=false"
            response = await self.delete_api(url, headers=self._headers(), payload={})
            return response.get("operation", {}).get("operationState") == "CREATED"
        return False

    async def set_brightness(self, ap_id: str, brightness: int):
        if await self.connect():
            brightness = max(0, min(100, brightness))
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/accesspoints/{ap_id}/lighting?prettyPrint=false"
            payload = json.dumps({"automatic": False, "intensity": brightness})
            response = await self.put_api(url, headers=self._headers(), payload=payload)
            return response.get("operation", {}).get("operationState") == "CREATED"
        return False

    async def restart_ap(self, ap_id: str):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/accesspoints/{ap_id}/reboot?prettyPrint=false"
            response = await self.post_api(url, headers=self._headers(), payload={})
            return response.get("operation", {}).get("operationState") == "CREATED"
        return False

    async def restart_system(self, system_id: str):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/reboot?prettyPrint=false"
            response = await self.post_api(url, headers=self._headers(), payload={})
            return response.get("operation", {}).get("operationState") == "CREATED"
        return False

    async def refresh_tokens(self):
        if await self.connect():
            creds = grpc.access_token_call_credentials(self._api_token)
            ssl = grpc.ssl_channel_credentials()
            composite = grpc.composite_channel_credentials(ssl, creds)
            channel = grpc.secure_channel("googlehomefoyer-pa.googleapis.com:443", composite)
            service = StructuresServiceStub(channel)
            resp = service.GetHomeGraph(GetHomeGraphRequest())
            data = resp.home.devices

            tokens = {}
            for device in data:
                if device.local_auth_token != "":
                    tokens[device.device_info.project_info.string2] = device.local_auth_token
            return tokens

    async def update_info(self, host):
        if await self.connect():
            url = f"https://{host}:8443/setup/eureka_info"
            params = {
                "params": "version,audio,name,build_info,detail,device_info,net,wifi,setup,settings,opt_in,opencast,multizone,proxy,night_mode_params,user_eq,room_equalizer",
                "options": "detail",
            }
            response = await self.get_api(url=url, params=params)
            if response:
                return response
            raise GoogleHomeUpdateFailed()

    async def get_bluetooth_status(self, host, token):
        if await self.connect():
            url = f"https://{host}:8443/setup/bluetooth/status"
            headers = {"cast-local-authorization-token": token}
            return await self.get_api(url=url, headers=headers)

    async def get_bluetooth_devices(self, host, token):
        if await self.connect():
            url = f"https://{host}:8443/setup/bluetooth/scan"
            headers = dict(GH_HEADERS)
            headers["Host"] = host
            headers["cast-local-authorization-token"] = token
            data = {"enable": True, "clear_results": True, "timeout": 5}

            await self.post_api(url=url, headers=headers, json_payload=data)
            await asyncio.sleep(5)

            url = f"https://{host}:8443/setup/bluetooth/scan_results"
            return await self.get_api(url=url, headers=headers)

    async def create_wan_speedtest(self, system_id: str):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/wanSpeedTest"
            response = await self.post_api(
                url=url,
                headers=self._headers(),
                payload={},
                params=(("prettyPrint", "false"),),
            )
            return response["operation"]["operationId"]

    async def check_operation(self, operation_id: str):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/operations/{operation_id}"
            return await self.get_api(
                url=url,
                headers=self._headers(),
                payload={},
                params=(("prettyPrint", "false"),),
            )

    async def speed_test_results(self, system_id: str):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/speedTestResults"
            response = await self.get_api(
                url=url,
                headers=self._headers(),
                payload={},
                params=(("prettyPrint", "false"), ("maxResultCount", 1)),
            )
            return response["speedTestResults"]

    async def run_speed_test(self, system_id: str):
        if await self.connect():
            operation_id = await self.create_wan_speedtest(system_id=system_id)
            status = (await self.check_operation(operation_id))["operationState"]

            while status != "DONE":
                await asyncio.sleep(5)
                status = (await self.check_operation(operation_id))["operationState"]

            results = await self.speed_test_results(system_id=system_id)
            return results[0]

    async def start_retrieve_sensitive_info(self, system_id: str, station_ids: list):
        if await self.connect():
            if not station_ids:
                return None
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/groups/{system_id}/stations/operations/sensitiveInfo"
            response = await self.post_api(
                url=url,
                headers=self._headers(),
                json_payload={"stationIds": station_ids},
                params=(("prettyPrint", "false"),),
            )
            return response.get("operation", {}).get("operationId")

    async def sensitive_info_results(self, operation_id: str):
        if await self.connect():
            url = f"https://googlehomefoyer-pa.googleapis.com/v2/operations/{operation_id}/sensitiveInfo"
            return await self.get_api(
                url=url,
                headers=self._headers(),
                payload={},
                params=(("prettyPrint", "false"),),
            )

    async def get_sensitive_info(self, system_id: str, station_ids: list):
        if not station_ids:
            return []

        if await self.connect():
            operation_id = await self.start_retrieve_sensitive_info(system_id=system_id, station_ids=station_ids)
            if not operation_id:
                return []

            status = (await self.check_operation(operation_id))["operationState"]
            while status != "DONE":
                await asyncio.sleep(5)
                status = (await self.check_operation(operation_id))["operationState"]

            results = await self.sensitive_info_results(operation_id=operation_id)
            return results.get("stationSensitiveInfos", [])


class GoogleWifiException(Exception):
    pass


class GoogleHomeUpdateFailed(Exception):
    pass


class GoogleHomeIgnoreDevice(Exception):
    pass
