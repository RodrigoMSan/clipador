# Configuracao inicial do Clipador: pede o token, descobre o chat e grava o .env
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host ""
Write-Host "=== Configuracao do Clipador ===" -ForegroundColor Cyan
while ($true) {
    $token = (Read-Host "Cole o token do BotFather (botao direito do mouse cola)").Trim()
    try {
        $me = Invoke-RestMethod "https://api.telegram.org/bot$token/getMe"
        Write-Host "Token OK: bot @$($me.result.username)" -ForegroundColor Green
        break
    } catch {
        Write-Host "Token invalido. Copie de novo a ultima mensagem do BotFather." -ForegroundColor Red
    }
}
$arroba = (Read-Host "Qual o nosso @ que aparece no fim do video (ex: @clipador)").Trim()
if (-not $arroba) { $arroba = "@clipador" }
if (-not $arroba.StartsWith("@")) { $arroba = "@$arroba" }
while ($true) {
    Write-Host "Mande /start para o bot @$($me.result.username) no Telegram e depois aperte Enter aqui."
    Read-Host | Out-Null
    $upd = Invoke-RestMethod "https://api.telegram.org/bot$token/getUpdates"
    $chat = ($upd.result | Where-Object { $_.message } | Select-Object -Last 1).message.chat.id
    if ($chat) { break }
    Write-Host "Ainda nao recebi o /start. Tente de novo." -ForegroundColor Yellow
}
$env_txt = "TELEGRAM_TOKEN=$token`nTELEGRAM_CHAT_ID=$chat`nCLIPADOR_ARROBA=$arroba`nCLIPADOR_PERIODOS=all,7d`nCLIPADOR_HORARIOS=10:00,18:00`n"
[IO.File]::WriteAllText("$PSScriptRoot\.env", $env_txt, (New-Object Text.UTF8Encoding $false))
Write-Host "Pronto! Configuracao salva (chat $chat)." -ForegroundColor Green
