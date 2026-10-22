# SmartRoadRouter

SmartRoadRouter is a **real-road trip-planning beta** for the Waterloo–
Collingwood corridor. It can search for places, use the Android device's
current location, request a driving route from a locally hosted
OpenStreetMap/OSRM road network, show current weather at the endpoints, and
hand directions off to Google Maps.

## What it does—and does not—do

- **Real road geometry:** `/route` uses the local OSRM service and Ontario
  OpenStreetMap road extract. It does not fall back to the synthetic graph if
  the local router is unavailable.
- **Place search and weather:** searches and current endpoint conditions use
  Open-Meteo services. Live weather failure is shown in the app and does not
  get replaced with made-up conditions.
- **Driving navigation:** the app opens Google Maps for driving directions.
  Google Maps calculates its own route, which may differ from the preview.
- **Not a safety-rated winter router:** the route preview is an ordinary
  driving route. Current weather is context only; it is not used to calculate
  a safety score. There is no live traffic, road-closure, collision, plowing,
  or road-surface feed. This app is not a substitute for Ontario 511, official
  weather alerts, road signs, or driver judgment.

Use it as an experimental trip-planning aid, not as a safety guarantee or
primary navigation system. The app and backend have not been validated for
emergency, commercial, or safety-critical use.

## Location and privacy

Place-search text is sent to Open-Meteo's geocoding service. When you plan a
route, the selected coordinates go to the API you configured, the OSRM server
you host, and Open-Meteo for endpoint weather. If you open Google Maps, those
coordinates are also sent to Google. The app does not intentionally store
location history, but the API host, network, or external providers may process
requests under their own policies.

## Requirements

- Windows 10/11 64-bit.
- Docker Desktop with the Linux container engine enabled.
- Python 3.11 or newer.
- Node.js 24 LTS and npm.
- Expo Go on an Android phone, or an Android emulator with Expo Go installed.
- Internet access for initial road-data download, place search, weather, and
  Google Maps navigation.

Preparing the Ontario road network downloads an approximately 1 GB PBF file
and creates additional routing data. Processing time, disk use, and memory
depend on the machine. The local OSRM service must stay running while routes
are requested.

## First-time setup on Windows

Run PowerShell commands from the repository root.

### 1. Prepare the self-hosted road router

```powershell
docker info
.\routing\osrm\prepare.ps1
docker compose -f routing/osrm/compose.yaml up -d
```

The script downloads Geofabrik's Ontario OpenStreetMap extract and runs the
OSRM car-profile preparation steps. The extract is ignored by Git and remains
on your machine. Verify the local router responds:

```powershell
Invoke-RestMethod "http://127.0.0.1:5000/route/v1/driving/-80.5204,43.4643;-80.2169,44.5011?overview=false"
```

The response should contain `"code": "Ok"`. If preparation fails for lack of
memory or disk, use a machine with more resources or prepare a smaller,
appropriately licensed regional extract before continuing.

### 2. Start the API

In a second PowerShell window:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
python -m src.api.main
```

The API listens on port 8000 and uses OSRM at `http://127.0.0.1:5000` by
default. Check <http://127.0.0.1:8000/health>. If PowerShell blocks activation,
use `.\.venv\Scripts\python.exe` in place of `python`.

### 3. Start the Android app

In a third PowerShell window:

```powershell
Set-Location mobile
npm install
npm run typecheck
npm run start
```

Install Expo Go from Google Play and scan the QR code to open the app. For an
Android emulator, use `npm run android`. To run the same client in a browser,
use `npm run web`.

To use a physical phone, copy `mobile\.env.example` to `mobile\.env` and set
`EXPO_PUBLIC_API_URL` to the computer's private LAN IPv4 address:

```dotenv
EXPO_PUBLIC_API_URL=http://192.168.1.23:8000
```

Restart Expo after changing `.env`. Keep the phone and computer on the same
trusted Wi-Fi network and allow Python through Windows Firewall on a private
network if prompted. The app requests foreground location permission when you
choose **Use this device's current location**.

For browser testing from another device, also set the backend's exact browser
origin before starting it, for example:

```powershell
$env:CORS_ORIGINS = "http://192.168.1.23:8081"
python -m src.api.main
```

### Use for a trip

Search for or select the start and destination, or use the device's current
location for the start. Select **Plan road route** to preview the road
distance, estimated duration, and current weather at each endpoint. Select
**Open driving directions in Google Maps** to hand off the trip.

The app's API address defaults to the Android emulator host (`10.0.2.2`) or
the local web host (`127.0.0.1`). A physical phone must use the computer's LAN
address as described above. If the phone leaves that network, it can no longer
reach a locally running API. **For use away from the development network, the
API and routing service need to be deployed on an internet-accessible host
with HTTPS and appropriate access controls.** This repository does not include
that production deployment; do not expose the development API or OSRM port
directly to the public internet.

## API

### `GET /health`

Returns `{"status":"healthy"}`.

### `GET /geocode?query=Waterloo%2C%20Ontario`

Searches for up to five place matches. Requires a query of at least three
characters. Results include labels and coordinates.

### `POST /route`

Requests a real driving route and current weather at its endpoints:

```json
{
  "origin_lat": 43.4643,
  "origin_lon": -80.5204,
  "dest_lat": 44.5011,
  "dest_lon": -80.2169
}
```

The response includes OSRM route geometry, estimated distance and duration,
OpenStreetMap attribution, and either current Open-Meteo conditions at both
endpoints or an explicit weather-unavailable status. A routing-service failure
returns an error; it never silently substitutes demo route data. These
estimates are not live-traffic estimates.

### `POST /demo/route`

Runs the earlier five-node synthetic Waterloo demonstration graph. It is only
for local development and tests; it is not used by the app's real `/route`
request.

## Data sources and attribution

- **Road network:** [OpenStreetMap](https://www.openstreetmap.org/) data
  distributed by [Geofabrik](https://download.geofabrik.de/north-america/canada/ontario.html).
  OpenStreetMap data is available under the Open Database License (ODbL);
  retain attribution and review the license obligations for your intended use.
- **Place search and weather:** [Open-Meteo](https://open-meteo.com/). Review
  its current API terms, attribution requirements, and usage limits before
  public or commercial deployment.
- **Turn-by-turn directions:** Google Maps, opened separately by the app.
  Google Maps recalculates the route and supplies its own navigation data.

The road graph is a dated extract, not a live roadworks/closure feed. Refresh
the extract periodically using the current Geofabrik file and rerun the OSRM
preparation steps. The current setup processes all of Ontario; it may need a
larger machine than the app/backend itself.

## Project status

- [x] Android-first Expo Go app and browser client.
- [x] Current-device location and place search.
- [x] Real road-route API backed by self-hosted OSRM and Ontario OSM data.
- [x] Current endpoint weather from Open-Meteo with explicit unavailable state.
- [x] Google Maps driving-directions handoff.
- [ ] Dedicated regional extract and automated road-data refresh.
- [ ] Ontario 511 incident/closure integration.
- [ ] Weather-aware alternative-route scoring with validated data and testing.
- [ ] Secure, monitored HTTPS deployment for use outside the local network.
- [ ] Operational validation before any safety-related claims.

## Repository layout

```text
SmartRoadRouter/
├── mobile/                 # Expo Go Android app and Expo web client
├── routing/
│   └── osrm/
│       ├── compose.yaml
│       └── prepare.ps1
├── src/
│   ├── api/
│   │   ├── main.py         # HTTP API
│   │   └── providers.py    # OSRM and Open-Meteo clients
│   └── routing/
│       └── engine.py       # Synthetic demo route only
├── tests/
└── README.md
```

## Troubleshooting

- **OSRM returns an error or `/route` responds with 503:** Check that OSRM is
  running with `docker compose -f routing/osrm/compose.yaml ps`, and that the
  route service responds at `http://127.0.0.1:5000`. The API does not switch to
  demo data.
- **Route returns 422:** The coordinates may not snap to a drivable road in
  the Ontario extract, or no route may connect them.
- **Place search or weather unavailable:** Check internet access. The app
  reports provider failure; weather is never filled in with synthetic values.
- **The phone cannot reach the API:** Use the computer's current private LAN
  address in `mobile\.env`, check the same Wi-Fi network, and allow Python
  through the private-network firewall.
- **Location is denied:** Enter a starting place through search or allow
  foreground location access in Android settings.
- **PowerShell activation is blocked:** Run the virtual environment's
  `Scripts\python.exe` directly; changing the global execution policy is not
  required.
