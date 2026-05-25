$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$d = Join-Path $root 'icons'
New-Item -ItemType Directory -Force -Path $d | Out-Null
Add-Type -AssemblyName System.Drawing
foreach ($s in 16, 32) {
  $b = New-Object System.Drawing.Bitmap $s, $s
  $r = [int]($s * 0.12)
  $cx = [int]($s * 0.35)
  $cy = [int]($s * 0.35)
  $cTeal = [System.Drawing.Color]::FromArgb(255, 13, 148, 136)
  $cWhite = [System.Drawing.Color]::FromArgb(255, 255, 255, 255)
  for ($x = 0; $x -lt $s; $x++) {
    for ($y = 0; $y -lt $s; $y++) {
      $dx = $x - $cx
      $dy = $y - $cy
      if (($dx * $dx + $dy * $dy) -lt ($r * $r)) {
        $b.SetPixel($x, $y, $cWhite)
      } else {
        $b.SetPixel($x, $y, $cTeal)
      }
    }
  }
  $out = Join-Path $d "canary-$s.png"
  $b.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
  $b.Dispose()
  Write-Output "Wrote $out"
}
