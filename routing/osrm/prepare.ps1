$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force -Path ".\data" | Out-Null
    $extract = ".\data\ontario-latest.osm.pbf"

    if (-not (Test-Path $extract)) {
        Write-Host "Downloading the Ontario OpenStreetMap extract (about 1 GB)..."
        Invoke-WebRequest `
            -Uri "https://download.geofabrik.de/north-america/canada/ontario-latest.osm.pbf" `
            -OutFile $extract
    }

    Write-Host "Preparing the road network. This can take a long time and needs substantial disk and memory."
    docker compose -f compose.yaml run --rm --entrypoint osrm-extract osrm `
        -p /opt/car.lua /data/ontario-latest.osm.pbf
    docker compose -f compose.yaml run --rm --entrypoint osrm-partition osrm `
        /data/ontario-latest.osrm
    docker compose -f compose.yaml run --rm --entrypoint osrm-customize osrm `
        /data/ontario-latest.osrm

    Write-Host "Road data prepared. Start the local router with:"
    Write-Host "docker compose -f routing/osrm/compose.yaml up -d"
}
finally {
    Pop-Location
}
