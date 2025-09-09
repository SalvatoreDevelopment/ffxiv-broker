# Script PowerShell per raccogliere dataset completo FFXIV Market
# Uso: .\scripts\run_dataset_collection.ps1 [-Test] [-Excel] [-World "Phoenix"]

param(
    [switch]$Test,
    [switch]$Excel,
    [string]$World = "Phoenix"
)

Write-Host "?? FFXIV Market Dataset Collection" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan

# Verifica che Poetry sia installato
try {
    $poetryVersion = poetry --version
    Write-Host "? Poetry trovato: $poetryVersion" -ForegroundColor Green
} catch {
    Write-Host "? Poetry non trovato. Installa Poetry prima di continuare." -ForegroundColor Red
    exit 1
}

# Verifica che le dipendenze siano installate
Write-Host "?? Verificando dipendenze..." -ForegroundColor Yellow
poetry install --quiet

if ($Test) {
    Write-Host "?? Modalita TEST - Raccolta subset limitato" -ForegroundColor Yellow
    Write-Host "?? Processando 8 item di test..." -ForegroundColor Yellow
    
    if ($Excel) {
        Write-Host "?? Creando file Excel..." -ForegroundColor Yellow
        $env:FFXIV_WORLD = $World
        poetry run python scripts/create_excel_dataset.py
        Write-Host "`n? Test completato!" -ForegroundColor Green
        Write-Host "?? File Excel salvato in: data/ffxiv_market_dataset.xlsx" -ForegroundColor Cyan
    } else {
        # Esegui test CSV (passa il world)
        $env:FFXIV_WORLD = $World
        poetry run python scripts/test_dataset.py
        Write-Host "`n? Test completato!" -ForegroundColor Green
        Write-Host "?? Risultati salvati in: data/test_dataset.csv" -ForegroundColor Cyan
        
        # Mostra anteprima risultati
        if (Test-Path "data/test_dataset.csv") {
            Write-Host "`n?? Anteprima risultati:" -ForegroundColor Yellow
            Get-Content "data/test_dataset.csv" | Select-Object -First 5 | ForEach-Object { Write-Host "   $_" }
        }
    }
} else {
    Write-Host "?? Modalita COMPLETA - Raccolta tutti gli item tradeable" -ForegroundColor Yellow
    Write-Host "??  ATTENZIONE: Questa operazione puo richiedere diverse ore!" -ForegroundColor Red
    Write-Host "?? Server: $World" -ForegroundColor Cyan
    
    $confirmation = Read-Host "`nVuoi continuare? (y/N)"
    if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
        Write-Host "? Operazione annullata." -ForegroundColor Red
        exit 0
    }
    
    Write-Host "`n?? Inizio raccolta dataset completo..." -ForegroundColor Yellow
    
    # Esegui raccolta completa (passa il world agli script)
    $env:FFXIV_WORLD = $World
    poetry run python scripts/collect_dataset.py
    
    Write-Host "`n? Raccolta completata!" -ForegroundColor Green
    Write-Host "?? Dataset salvato in: data/ffxiv_market_dataset.csv" -ForegroundColor Cyan
    
    # Mostra statistiche finali
    if (Test-Path "data/ffxiv_market_dataset.csv") {
        $totalLines = (Get-Content "data/ffxiv_market_dataset.csv" | Measure-Object -Line).Lines - 1
        Write-Host "?? Totale item processati: $totalLines" -ForegroundColor Yellow
    }
}

Write-Host "`n?? Prossimi passi:" -ForegroundColor Cyan
Write-Host "   - Apri il file CSV/Excel in Excel o un editor di testo" -ForegroundColor White
Write-Host "   - Analizza i dati per trovare opportunita di trading" -ForegroundColor White
Write-Host "   - Filtra per flags 'flip' per opportunita immediate" -ForegroundColor White
Write-Host "   - Evita item con flag 'saturo' per investimenti a lungo termine" -ForegroundColor White
