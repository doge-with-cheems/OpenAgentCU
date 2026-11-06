$ErrorActionPreference = "Stop"

$out = Join-Path $PSScriptRoot "OpenAgentCU.ico"
$size = 256

Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.Clear([System.Drawing.Color]::FromArgb(15, 23, 42))

$teal = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(13, 148, 136))
$g.FillEllipse($teal, 18, 18, 220, 220)

$white = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 10)
$white.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
$white.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
$g.DrawRectangle($white, 58, 62, 140, 94)
$g.DrawLine($white, 128, 156, 128, 182)
$g.DrawLine($white, 98, 190, 158, 190)

$dot = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(15, 23, 42))
$g.FillEllipse($dot, 106, 94, 44, 30)

$hicon = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($hicon)
$stream = [System.IO.File]::Create($out)
$icon.Save($stream)
$stream.Close()

$g.Dispose()
$bmp.Dispose()
$icon.Dispose()

Write-Output ("icon: " + $out + " (" + (Get-Item $out).Length + " bytes)")
