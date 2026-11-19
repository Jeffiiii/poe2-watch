# Upload finished PoE2 recordings to Cloudflare R2; delete the local copy only after rclone has verified them.
# Prereq (once): an rclone remote named "r2" (see README.md). Run after OBS has STOPPED recording (Ctrl+F11).
param(
  [string]$Source = "C:\Users\Leo12\Videos\poe2-raw",
  [string]$Dest   = "r2:vision-model/poe2-raw",
  [switch]$KeepLocal
)
$ErrorActionPreference = "Stop"
$files = Get-ChildItem $Source -File | Where-Object { $_.Extension -in ".mp4", ".json", ".csv" -and $_.LastWriteTime -lt (Get-Date).AddMinutes(-2) }
if (-not $files) { Write-Host "nothing to upload"; exit 0 }
"{0} file(s), {1:N1} GB" -f $files.Count, (($files | Measure-Object Length -Sum).Sum / 1GB)
# rclone copy checks size + hash (MD5 ETag single-part, SHA256/MD5 metadata multipart) before it reports success.
& rclone copy $Source $Dest --include "*.mp4" --include "*.json" --include "*.csv" --min-age 2m --transfers 2 --checkers 4 --s3-chunk-size 64M --progress --stats-one-line
if ($LASTEXITCODE -ne 0) { throw "rclone copy failed ($LASTEXITCODE); local files kept" }
# Independent re-check of everything local against the bucket.
& rclone check $Source $Dest --include "*.mp4" --include "*.json" --include "*.csv" --min-age 2m --one-way
if ($LASTEXITCODE -ne 0) { throw "rclone check found differences; local files kept" }
if ($KeepLocal) { Write-Host "verified; local copies kept (-KeepLocal)"; exit 0 }
foreach ($f in $files) { Remove-Item $f.FullName -Force; Write-Host "deleted local $($f.Name)" }
Write-Host "done: uploaded and verified $($files.Count) file(s) to $Dest"
