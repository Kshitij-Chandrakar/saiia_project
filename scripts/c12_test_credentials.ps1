param([switch]$Clear, [switch]$GenerateWebhookSecret)

$ErrorActionPreference = 'Stop'
$env:BILLING_ENABLED = 'false'
$names = @('RAZORPAY_TEST_KEY_ID', 'RAZORPAY_TEST_KEY_SECRET', 'RAZORPAY_TEST_ACCOUNT_ID', 'RAZORPAY_TEST_WEBHOOK_SECRET', 'RAZORPAY_TEST_PREVIOUS_WEBHOOK_SECRET')
foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
if ($Clear) {
    if ($env:C12_WEBHOOK_CLIPBOARD_HASH) {
        $clipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue
        if ($clipboard -and $clipboard.Length -lt 1024) {
            $hash = [Security.Cryptography.SHA256]::Create()
            try {
                $currentHash = [Convert]::ToBase64String($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($clipboard)))
                if ($currentHash -ceq $env:C12_WEBHOOK_CLIPBOARD_HASH) { Set-Clipboard -Value '' }
            } finally { $hash.Dispose(); $clipboard=$null }
        }
        [Environment]::SetEnvironmentVariable('C12_WEBHOOK_CLIPBOARD_HASH',$null,'Process')
    }
    Write-Host 'Test credentials cleared; billing disabled.'; return
}

function Read-HiddenValue([string]$label) {
    $secure = Read-Host $label -AsSecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        $secure.Dispose()
    }
}

$values = @{}
try {
    foreach ($name in $names[0..2]) { $values[$name] = Read-HiddenValue $name }
    if ($GenerateWebhookSecret) {
        $bytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes); $values.RAZORPAY_TEST_WEBHOOK_SECRET = [Convert]::ToBase64String($bytes) }
        finally { $rng.Dispose(); [Array]::Clear($bytes,0,$bytes.Length) }
    } else {
        $values.RAZORPAY_TEST_WEBHOOK_SECRET = Read-HiddenValue 'RAZORPAY_TEST_WEBHOOK_SECRET'
    }
    if ($values.RAZORPAY_TEST_KEY_ID -cnotmatch '^rzp_test_[A-Za-z0-9]+$' -or
        [string]::IsNullOrWhiteSpace($values.RAZORPAY_TEST_KEY_SECRET) -or $values.RAZORPAY_TEST_KEY_SECRET -match '\s' -or
        $values.RAZORPAY_TEST_ACCOUNT_ID -cnotmatch '^acc_[A-Za-z0-9]+$' -or
        $values.RAZORPAY_TEST_WEBHOOK_SECRET.Length -lt 32) {
        throw 'Invalid test credential format. Nothing loaded; billing remains disabled.'
    }
    foreach ($name in $names[0..3]) { [Environment]::SetEnvironmentVariable($name, $values[$name], 'Process') }
    if ($GenerateWebhookSecret) {
        Set-Clipboard -Value $values.RAZORPAY_TEST_WEBHOOK_SECRET
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $env:C12_WEBHOOK_CLIPBOARD_HASH=[Convert]::ToBase64String($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($values.RAZORPAY_TEST_WEBHOOK_SECRET))) }
        finally { $hash.Dispose() }
        Write-Host 'Fresh webhook secret generated and copied to clipboard. Use it in the new Razorpay webhook Secret field.'
    }
    Write-Host 'Test credentials loaded into this process only; billing remains disabled.'
} finally {
    $values.Clear()
}
