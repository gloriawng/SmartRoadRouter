# SmartRoadRouter

SmartRoadRouter is a prototype for comparing a quick road route with one that
accounts for winter-weather risk. The first version runs locally with Python's
standard library and a small synthetic Waterloo-area road network. It needs no
external data downloads or API keys.

> **Prototype limitation:** The included road network and risk values are
> illustrative, not live road or weather data. Do not use its routes for real
> travel or safety decisions.

## Run the prototype on Windows

Python 3.11 or newer is recommended. No Conda environment or third-party
packages are needed for this prototype.

```powershell
# From the project root
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
python -m src.api.main
```

The API listens on port `8000`. If PowerShell prevents virtual
environment activation, run the venv's Python directly instead:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m src.api.main
```

Open <http://127.0.0.1:8000/health> to check the server. The interactive route
API is described below.

## Android and web app (Expo Go)

The `mobile/` app is a React Native + Expo client. Use Expo Go to run it on an
Android phone, or run the same interface in a web browser with Expo's web
target. Expo Go is a mobile app; web development runs in a browser using
React Native Web. Use Node.js 24.3+ LTS (or another version supported by the
Expo SDK) and npm.

Start the backend in one terminal from the repository root:

```powershell
python -m src.api.main
```

Start the app in another terminal:

```powershell
cd mobile
npm install
npm run start
```

Install Expo Go from Google Play and scan the development QR code with Expo Go
to use a physical Android phone. To launch an installed Android emulator
instead, use `npm run android`. To run the browser version:

```powershell
npm run web
```

The app defaults to `http://10.0.2.2:8000` on Android (the Android Emulator's
host-machine address) and `http://127.0.0.1:8000` on web. For a physical phone,
copy `mobile/.env.example` to `mobile/.env`, set `EXPO_PUBLIC_API_URL` to the
computer's LAN IPv4 address, restart Expo, and keep the phone and computer on
the same trusted Wi-Fi network. For example:

```dotenv
EXPO_PUBLIC_API_URL=http://192.168.1.23:8000
```

The backend binds to all network interfaces so a phone on the LAN can reach it.
Allow Python through Windows Firewall on a **private network** if prompted.
This demo API has no authentication; do not expose it to the public internet
or an untrusted network. Browser requests from localhost are allowed by
default. If the web app is served from another origin, configure its exact
origin with `CORS_ORIGINS` before starting the backend (for example,
`$env:CORS_ORIGINS = "http://192.168.1.23:8081"`). Expo Go's native requests
do not use browser CORS.

The screen includes route endpoints, manual weather inputs, quicker/balanced/
safer priority choices, and route results. Its location choices and route data
are illustrative, matching the backend's small synthetic network. Real GPS,
maps, live weather, and 511 events are not connected yet.

## Prototype API

### `GET /health`

Returns `{"status":"healthy"}`.

### `POST /route`

Coordinates are snapped to the nearest node in the demo graph. Each endpoint
must be within 3 km of a demo node. `safety_weight` ranges from `0` (optimize
for estimated travel time) to `1` (give weather-related road risk more weight).
Weather fields default to zero.

```json
{
  "origin_lat": 43.4643,
  "origin_lon": -80.5204,
  "dest_lat": 43.449,
  "dest_lon": -80.475,
  "safety_weight": 0.7,
  "weather": {
    "snowfall_cm_per_hour": 4,
    "wind_kmh": 50,
    "temperature_c": -5
  }
}
```

The response contains the selected route's node coordinates, baseline travel
time, distance, average road-risk score, weather severity, and generalized
routing cost. The baseline travel time does not model traffic or winter
slowdowns. Invalid requests return HTTP 400; coordinates outside the demo
coverage return HTTP 422.

## Project outline

### Phase 1 — Working local prototype

- [x] Define a small, synthetic directed road graph around Waterloo.
- [x] Find nearest graph nodes for submitted coordinates.
- [x] Compare route costs with Dijkstra's algorithm.
- [x] Blend estimated travel time with road risk and weather severity.
- [x] Provide health and route endpoints over local HTTP.
- [x] Cover routing and API behavior with standard-library unit tests.

### Phase 2 — Real road network

- Replace the synthetic graph with an OpenStreetMap road network using OSMnx.
- Choose a bounded study area and persist downloaded graph data locally.
- Derive road attributes such as length, road class, surface, and speed where
  available; document how missing or estimated attributes are handled.
- Add geographic data validation and tests before using external datasets.

### Phase 3 — Weather and road events

- Add a weather provider adapter for Environment and Climate Change Canada.
- Add an Ontario 511 provider adapter for active road events; keep API keys and
  other credentials out of source control.
- Define event freshness, geographic matching, units, and behavior when a
  provider is unavailable.
- Keep the local synthetic-data mode available for offline development.

### Phase 4 — Risk model and routing quality

- Calibrate risk inputs and the time-versus-safety trade-off against documented
  assumptions and suitable historical data.
- Add elevation/slope and collision-history features only after sourcing and
  validating those datasets.
- Compare routes using measurable outcomes, including travel time, distance,
  risk score, and route changes under different weather.
- Make the limitations and intended use of each risk score explicit.

### Phase 5 — Client and deployment

- [x] Add an Android-first Expo Go app and browser-based Expo web client.
- [ ] Add a map UI and route comparison visualization.
- Add persistence, caching, observability, and deployment configuration when
  the data and service requirements are known.
- Reassess API framework, authentication, rate limits, and operational safety
  before exposing the service beyond localhost.

## Planned data sources

| Data | Candidate source | Current status |
| --- | --- | --- |
| Road network | OpenStreetMap via OSMnx or a regional BBBike extract | Planned; not used by the prototype |
| Municipal roads | City of Waterloo Open Data / ArcGIS REST | Planned; check the service's current URL, fields, and license before use |
| Road events | Ontario 511 | Planned; confirm current API access and credential requirements |
| Weather | Environment and Climate Change Canada | Planned; provider adapter not yet implemented |
| Elevation | NASA SRTM or another appropriately licensed elevation source | Later phase |
| Collision history | City of Waterloo or another authorized data provider | Requires sourcing and access review |

Do not assume downloaded data is current, complete, or licensed for every use.
Record source, retrieval time, coordinate reference system, and license when
real datasets are introduced.

## Later geospatial environment

The prototype itself has no external dependencies. When Phase 2 begins, create
a separate Conda environment and install the compiled geospatial packages
together from conda-forge to reduce binary dependency conflicts:

```powershell
conda create -n winter-routing python=3.12 -y
conda activate winter-routing
conda install -c conda-forge geopandas osmnx rasterio fiona pyproj shapely networkx -y
conda env export --from-history > environment.yml
```

Recreate that environment with `conda env create -f environment.yml`. Add
weather, API, and machine-learning dependencies only when their respective
phases are implemented; the current local API intentionally uses the standard
library.

## Repository layout

```text
SmartRoadRouter/
├── mobile/                 # Expo Go Android app and Expo web client
│   ├── App.tsx
│   ├── app.json
│   └── package.json
├── src/
│   ├── api/
│   │   └── main.py
│   └── routing/
│       └── engine.py
├── tests/
│   └── test_routing.py
├── py-version.py        # Earlier OSMnx experiment; not required by the prototype
└── README.md
```

## Troubleshooting

- **`py` is not recognized:** Install Python 3.11+ and enable the Python
  launcher, or use the full path to the installed Python executable.
- **Virtual environment activation is blocked:** Use the venv's
  `Scripts\python.exe` directly as shown above; changing the machine's script
  execution policy is not required.
- **Port 8000 is in use:** Set another port before starting the server, for
  example `$env:PORT = "8001"; python -m src.api.main`.
- **Route request returns HTTP 422:** The demo only covers a small area around
  the included Waterloo nodes. A real regional road network is a later phase.
- **An older script reports missing OSMnx/NetworkX/Matplotlib/Folium:** Those
  packages are not needed by this prototype; see the later geospatial setup
  above if working on the earlier OSMnx experiment.
