# Base de datos DESECHABLE para correr los tests (nunca toca tu base local ni producción).
#
#   .\scripts\test_db.ps1 start   -> crea/levanta un Postgres temporal en el puerto 5499
#   .\scripts\test_db.ps1 stop    -> lo apaga
#   .\scripts\test_db.ps1 reset   -> lo apaga y borra sus datos (se recrea en el próximo start)
#
# Después de "start", correr los tests desde la carpeta backend:
#   $env:TEST_DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:5499/zola_test"
#   .\venv\Scripts\python.exe -m pytest
param(
    [Parameter(Position = 0)][ValidateSet("start", "stop", "reset")][string]$Action = "start",
    [string]$PgBin = "F:\Dev\Tools\pgsql\bin",
    [int]$Port = 5499
)
$ErrorActionPreference = "Stop"
$DataDir = Join-Path $env:TEMP "zola_test_pgdata"
$LogFile = Join-Path $env:TEMP "zola_test_pg.log"

function Stop-TestDb {
    if (Test-Path (Join-Path $DataDir "postmaster.pid")) {
        & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir -m fast stop | Out-Null
    }
}

switch ($Action) {
    "start" {
        if (-not (Test-Path (Join-Path $DataDir "PG_VERSION"))) {
            & (Join-Path $PgBin "initdb.exe") -D $DataDir -U postgres --auth=trust -E UTF8 | Out-Null
        }
        if (-not (Test-Path (Join-Path $DataDir "postmaster.pid"))) {
            # Ventana oculta propia y sin -Wait: así el servidor queda independiente de esta
            # consola (con -Wait o compartiendo la consola, PowerShell se queda esperándolo).
            Start-Process -FilePath (Join-Path $PgBin "pg_ctl.exe") -ArgumentList @("-D", "`"$DataDir`"", "-o", "`"-p $Port`"", "-l", "`"$LogFile`"", "start") -WindowStyle Hidden
        }
        for ($i = 0; $i -lt 30; $i++) {
            & (Join-Path $PgBin "pg_isready.exe") -h 127.0.0.1 -p $Port -U postgres | Out-Null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 1
        }
        & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='zola_test'" | Set-Variable exists
        if (-not $exists) { & (Join-Path $PgBin "createdb.exe") -h 127.0.0.1 -p $Port -U postgres zola_test }
        Write-Host "Postgres de pruebas listo: postgresql+psycopg://postgres@127.0.0.1:$Port/zola_test"
    }
    "stop" { Stop-TestDb; Write-Host "Postgres de pruebas detenido." }
    "reset" { Stop-TestDb; if (Test-Path $DataDir) { Remove-Item -Recurse -Force $DataDir }; Write-Host "Datos de pruebas borrados." }
}
