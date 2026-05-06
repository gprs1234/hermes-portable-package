# MT4 EA Heartbeat — runs on Windows
# Writes heartbeat to a location accessible from WSL
#
# SETUP INSTRUCTIONS — Windows Scheduled Task:
# ==============================================
# 1. Open Task Scheduler (taskschd.msc)
# 2. Click "Create Basic Task"
# 3. Name: "MT4 EA Heartbeat"
# 4. Trigger: "Daily", then modify to repeat every 2 minutes
# 5. Action: "Start a program"
#    Program: powershell.exe
#    Arguments: -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\User\.hermes\scripts\windows_ea_heartbeat.ps1"
# 6. Check "Open the Properties dialog" after finishing
# 7. In Properties:
#    - General: "Run whether user is logged on or not"
#    - Settings: "If task fails, restart every 1 minute" up to 3 attempts
#    - Conditions: Uncheck "Start only if on AC power"
#
# Alternative (from elevated PowerShell):
#   $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"C:\Users\User\.hermes\scripts\windows_ea_heartbeat.ps1`""
#   $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 9999)
#   Register-ScheduledTask -TaskName "MT4 EA Heartbeat" -Action $action -Trigger $trigger -RunLevel Highest -User "User"
# ==============================================

$heartbeatPath = "C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\CFDC9320EF2C819B475E6276F04DD44D\MQL4\Files\ea_heartbeat.json"

$heartbeat = @{
    timestamp = (Get-Date -Format "o")
    mt4_running = (Get-Process -Name "terminal64" -ErrorAction SilentlyContinue) -ne $null
    ea_files_dir = (Test-Path "C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\CFDC9320EF2C819B475E6276F04DD44D\MQL4\Files")
    latest_csv = $null
    csv_age_seconds = $null
}

# Check latest CSV
$csvDir = "C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\CFDC9320EF2C819B475E6276F04DD44D\MQL4\Files"
$latestCsv = Get-ChildItem -Path $csvDir -Filter "*.csv" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestCsv) {
    $heartbeat.latest_csv = $latestCsv.Name
    $heartbeat.csv_age_seconds = [math]::Round(((Get-Date) - $latestCsv.LastWriteTime).TotalSeconds, 1)
}

$heartbeat | ConvertTo-Json | Out-File -FilePath $heartbeatPath -Encoding UTF8
