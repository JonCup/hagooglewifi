# Google WiFi Home Assistant Integration

This fork provides control and monitoring of Google Wifi / Nest Wifi systems in Home Assistant using the Google Home Foyer API path and a `gpsoauth` token bundle.

## What this fork changes

The original integration depended on the older Google Wifi refresh-token flow. That flow is no longer reliable and may fail with HTTP 400.

This fork includes a local patched API client at:

```text
custom_components/googlewifi/googlewifi_api.py
```

The integration now imports that local client instead of the external `googlewifi` package.

## Supported platforms

### Binary sensor

Shows Google Wifi systems and access points, including their connection status.

Service: `googlewifi.reset`

| Parameter | Description | Example |
| --- | --- | --- |
| `entity_id` | Access point or system to restart. | `binary_sensor.this_access_point` |

### Device tracker

Reports connected and away status for devices registered in your Google Wifi network.

Google Wifi may retain old device data for a long time, so duplicate or stale devices may appear.

### Switch

Allows internet access for connected devices to be paused or resumed.

Service: `googlewifi.prioritize`

| Parameter | Description | Example |
| --- | --- | --- |
| `entity_id` | Device to prioritize. | `switch.my_iphone` |
| `duration` | Duration in hours. | `4` |

Service: `googlewifi.prioritize_reset`

| Parameter | Description | Example |
| --- | --- | --- |
| `entity_id` | Device or system entity used to clear prioritization. | `switch.my_iphone` |

Only one device can be prioritized at a time.

### Light

Allows the light brightness on each Google Wifi hub to be controlled.

### Sensor

Adds upload and download speed monitoring for the Google Wifi system. Automatic speed testing can be enabled or disabled from integration options.

Service: `googlewifi.speed_test`

| Parameter | Description | Example |
| --- | --- | --- |
| `entity_id` | Speed sensor entity for the Google Wifi system. | `sensor.google_wifi_system_upload_speed` |

Only the main Wifi system can be tested. Individual devices cannot run speed tests.

## Install through HACS

1. Open HACS.
2. Add this repository as a custom integration repository:

```text
https://github.com/JonCup/hagooglewifi
```

3. Install **Google WiFi**.
4. Restart Home Assistant.

## Manual install

Copy this folder from the repo:

```text
custom_components/googlewifi
```

Into your Home Assistant config folder:

```text
/config/custom_components/googlewifi
```

Then restart Home Assistant.

## Configure the integration

This fork expects a `gpsoauth` token bundle in this format:

```text
gps:<google_email>:<android_id>:<google_master_token>
```

Paste the full `gps:...` value into the Google WiFi integration setup screen.

Treat this value like a password. Do not commit it, share it, or paste it into logs.

After installing and restarting Home Assistant:

1. Go to **Settings -> Devices & services**.
2. Click **Add integration**.
3. Search for **Google WiFi**.
4. Paste the full `gps:...` token bundle.
5. Submit the form.

## Updating from the manually patched local copy

If you previously patched `/config/custom_components/googlewifi` by hand, replace that local folder with the version from this repo after this PR is merged.

Recommended path:

1. Back up your current Home Assistant config.
2. Remove or replace `/config/custom_components/googlewifi`.
3. Install this fork through HACS, or copy the repo version manually.
4. Restart Home Assistant.
5. Confirm the existing Google WiFi integration still loads with the same `gps:...` token bundle.

Do not keep old `.bak-*` files inside the integration folder. They are only backups from the manual patch process and are not part of the integration.
