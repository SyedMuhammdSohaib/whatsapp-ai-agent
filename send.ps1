param([string]$to, [string]$msg)
$body = @{ recipient = $to; message = $msg } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8080/api/send" -Method Post -ContentType "application/json" -Body $body
