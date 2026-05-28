# Google WiFi Home Assistant Integration

<a target="_blank" href="https://www.buymeacoffee.com/djtimca"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy me a coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;"></a> [![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)

This integration provides control and monitoring of the Google WiFi system within Home Assistant.

### Platforms:

#### Binary Sensor:

The binary_sensor platform will show the access points that are configured in your system and their connection status to the Internet (on = connected).

Additionally there is a custom service to allow you to reset either a single access point or the whole wifi system:

##### Service: googlewifi.reset

|Parameter|Description|Example|
|-|-|-|
|entity_id|Access point or system to restart.|binary_sensor.this_access_point|

#### Device Tracker:

The device_tracker platform will report the connected (home/away) status of all of the devices which are registered in your Google Wifi network. Note: Google Wifi retains device data for a long time so you should expect to see many duplicated devices which are not connected as part of this integration. There is no way to parse out what is current and what is old.

#### Switch:

The switch platform will allow you to turn on and off the internet to any connected device in your Google Wifi system. On = Internet On, Off = Internet Off / Paused. Additionally there are two custom services to allow you to set and clear device prioritization.

##### Service: googlewifi.prioritize

|Parameter|Description|Example|
|-|-|-|
|entity_id|The entity_id of the device you want to prioritize.|switch.my_iphone|
|duration|The duration in hours that you want to prioritize for.|4|

##### Service: googlewifi.prioritize_reset

|Parameter|Description|Example|
|-|-|-|
|entity_id|The entity_id of a device on the system you want to clear.|switch.my_iphone|

Note: Only one device can be prioritized at a time. If you set a second prioritization it will clear the first one first.

#### Light:

The light platform allows you to turn on and off and set the brightness of the lights on each of your Google Wifi hubs. Just for fun.

#### Sensor:

The sensor platform adds upload and download speed monitoring to your Google Wifi system. Automatic speed testing can be enabled and disabled from the integration options (default on), as can the interval for the tests (default 24 hours).

##### Service: googlewifi.speed_test

|Parameter|Description|Example|
|-|-|-|
|entity_id|A speed sensor entity_id of the google system.|sensor.google_wifi_system_upload_speed|

Note: You must select the main wifi system. Individual devices can not be tested.

### Install through HACS:

Add a custom repository in HACS pointed to https://github.com/JonCup/hagooglewifi

The new integration for Google WiFi should appear under your integrations tab.

Click Install and restart Home Assistant.

### Install manually:

Copy the contents found in https://github.com/JonCup/hagooglewifi/tree/main/custom_components/googlewifi to your `custom_components/googlewifi` folder in Home Assistant.

Restart Home Assistant.

## Configure the integration

This fork uses the patched `gpsoauth` / Google Home Foyer auth path. The older OnHub Auth Tool / `oauthaccountmanager issueToken` refresh-token flow is no longer reliable and may return HTTP 400.

The integration token field expects the full token bundle from the patched auth helper flow:

```text
gps:<google_email>:<android_id>:<google_master_token>
```

Paste the entire `gps:...` value into the Google WiFi integration setup screen. Treat this value like a password. It grants access to the Google account path used by the integration.

Once installed, restart Home Assistant and go to Settings -> Devices & services -> Add integration.

Search for Google WiFi and you will see the integration available.

Enter the token bundle in the integration configuration screen and hit submit.

## Create a patch from an installed Home Assistant copy

If you patched the integration directly inside Home Assistant, export the installed copy as a patch against this repo before committing it.

The installed integration should live here:

```text
/config/custom_components/googlewifi/
```

Run this from the Home Assistant terminal or SSH add-on:

```bash
set -euo pipefail

REPO="https://github.com/JonCup/hagooglewifi.git"
WORKDIR="/tmp/hagooglewifi-patch"
INSTALLED="/config/custom_components/googlewifi"
PATCH_OUT="/config/googlewifi-installed.patch"

rm -rf "$WORKDIR"
git clone --depth=1 "$REPO" "$WORKDIR"

if [ ! -d "$INSTALLED" ]; then
  echo "Installed integration not found: $INSTALLED" >&2
  exit 1
fi

rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$INSTALLED"/ "$WORKDIR/custom_components/googlewifi"/

git -C "$WORKDIR" diff -- custom_components/googlewifi > "$PATCH_OUT"

if [ ! -s "$PATCH_OUT" ]; then
  echo "No differences found. Patch file is empty: $PATCH_OUT"
else
  echo "Patch written to: $PATCH_OUT"
fi
```

To apply the patch to a fresh clone later:

```bash
git clone https://github.com/JonCup/hagooglewifi.git
cd hagooglewifi
git apply /path/to/googlewifi-installed.patch
```

Enjoy!
