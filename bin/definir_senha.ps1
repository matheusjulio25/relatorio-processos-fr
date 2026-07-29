# Grava PJE_SENHA no .env sem exibir a senha na tela nem deixá-la no histórico
# do shell. Equivalente Windows do bin/cofre.sh (que usa o Keychain do macOS).
#
# Uso:  powershell -ExecutionPolicy Bypass -File bin\definir_senha.ps1

$ErrorActionPreference = 'Stop'

$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
if (-not (Test-Path $envPath)) { throw ".env não encontrado em $envPath" }

$secure = Read-Host 'Senha do PJe' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $senha = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if ([string]::IsNullOrWhiteSpace($senha)) { throw 'senha vazia — nada foi gravado' }

$achou = $false
$novas = foreach ($linha in (Get-Content $envPath -Encoding utf8)) {
    if ($linha -match '^PJE_SENHA=') { $achou = $true; "PJE_SENHA=$senha" } else { $linha }
}
if (-not $achou) { $novas = @($novas) + "PJE_SENHA=$senha" }

# UTF-8 sem BOM: o .env é lido pelo python-dotenv.
[IO.File]::WriteAllLines($envPath, [string[]]$novas, (New-Object Text.UTF8Encoding $false))

Write-Host "PJE_SENHA gravada em $envPath ($($senha.Length) caracteres)."
Write-Host "Teste com: .venv\Scripts\python.exe -m coletor_pje.cli --no-headless pericias"
