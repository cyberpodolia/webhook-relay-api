param(
    [Parameter(Mandatory = $true)]
    [string]$Scenario,
    [string]$Target = "http://host.docker.internal:8000",
    [string]$InfluxUrl = "http://localhost:8086/k6"
)

$scriptPath = "./k6/scenarios/$Scenario"
if (-not (Test-Path $scriptPath)) {
    throw "Scenario not found: $scriptPath"
}

docker run --rm -i `
  --network perfnet `
  -e TARGET_URL=$Target `
  -v "${PWD}:/work" `
  -w /work `
  grafana/k6:0.51.0 run -o influxdb=$InfluxUrl $scriptPath
