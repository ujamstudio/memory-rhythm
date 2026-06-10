<#
  deploy-aws.ps1 — one-shot AWS deploy for Memory Rhythm (single EC2 host).

  WHAT IT DOES (all via AWS CLI, no Docker / no IAM role / no GitHub):
    1. Bundles backend/ (app + static frontend + requirements.txt) -> deploy.tar.gz
    2. Uploads it to a fresh S3 bucket and makes a 1-hour presigned URL
    3. Creates a security group (inbound 80, and 22 if you pass -KeyName)
    4. Launches one Ubuntu 24.04 (Python 3.12) t3.micro instance whose user-data
       downloads the bundle, pip-installs, and runs uvicorn on :80 via systemd
    5. Prints the public URL

  PREREQS (you do these once — I cannot do them for you):
    - AWS CLI installed and `aws configure` done (access key + secret + region)
    - A default VPC in the region (almost always present)

  COST: t3.micro is free-tier eligible (750 h/mo for 12 months). S3 + data are
  a few cents. TEAR DOWN with deploy/destroy-aws.ps1 when done.

  USAGE:
    pwsh deploy/deploy-aws.ps1                       # mock AI (stable, no secret)
    pwsh deploy/deploy-aws.ps1 -Gemini               # real Gemini (reads backend/.env)
    pwsh deploy/deploy-aws.ps1 -Region us-east-1 -KeyName my-keypair
#>
[CmdletBinding()]
param(
  [string]$Region = "",                 # default: your `aws configure` region
  [string]$InstanceType = "t3.micro",
  [switch]$Gemini,                       # inject GOOGLE_API_KEY from backend/.env
  [string]$KeyName = "",                 # optional EC2 key pair name (enables SSH:22)
  [string]$Tag = "memory-rhythm",
  [switch]$NoEip,                        # skip re-attaching the tagged Elastic IP
  [switch]$Https,                        # front the app with Caddy + Let's Encrypt (nip.io); needs a tagged EIP
  [switch]$Eleven,                       # enable ElevenLabs TTS (reads ELEVENLABS_* from backend/.env)
  [switch]$Polly                         # enable Amazon Polly TTS (Korean Seoyeon) via an IAM instance role
)
if ($Eleven -and $Polly) { throw "Choose one TTS: -Eleven or -Polly, not both." }
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot          # repo root (deploy/ is one below)
$backend = Join-Path $repo "backend"

# NOTE: must NOT be named "Aws" — PowerShell command resolution is case-insensitive,
# so a function named Aws would shadow the external `aws` CLI and recurse infinitely.
function AwsChecked { param([Parameter(ValueFromRemainingArguments)]$a) & aws.exe @a; if ($LASTEXITCODE) { throw "aws $($a -join ' ') failed ($LASTEXITCODE)" } }

# --- preflight ------------------------------------------------------------
& aws --version 2>&1 | Out-Null; if ($LASTEXITCODE) { throw "AWS CLI not installed. Install it, then run `aws configure`." }
if (-not $Region) { $Region = (& aws configure get region) }
if (-not $Region) { throw "No region. Pass -Region or set one via `aws configure`." }
$acct = (& aws sts get-caller-identity --query Account --output text)
if ($LASTEXITCODE) { throw "Not authenticated. Run `aws configure` first." }
Write-Host "Account $acct · region $Region · type $InstanceType" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $backend "static/index.html"))) {
  throw "backend/static is missing. Build first: (cd frontend; npx vite build) then copy dist -> backend/static."
}

# --- 1) bundle ------------------------------------------------------------
$bundle = Join-Path $env:TEMP "memrhythm-deploy.tar.gz"
if (Test-Path $bundle) { Remove-Item $bundle -Force }
Write-Host "Bundling backend/ (excluding .env, __pycache__)..." -ForegroundColor Cyan
& tar -czf $bundle -C $backend --exclude=".env" --exclude="__pycache__" --exclude="*.pyc" app static requirements.txt seed_demo.py
if ($LASTEXITCODE) { throw "tar bundling failed." }
$sizeMB = [math]::Round((Get-Item $bundle).Length / 1MB, 2)
Write-Host "  bundle: $bundle ($sizeMB MB)" -ForegroundColor DarkGray

# --- 2) S3 upload + presign ----------------------------------------------
# Bucket name must be globally unique + lowercase. (account+region keep it stable-ish.)
$bucket = "memrhythm-deploy-$acct-$Region".ToLower()
$key = "deploy.tar.gz"
# head-bucket fails (and writes stderr) when the bucket is absent; under
# $ErrorActionPreference=Stop that native stderr is a terminating error in
# Windows PowerShell 5.1, so catch it and treat any failure as "absent".
$exists = $false
try { & aws.exe s3api head-bucket --bucket $bucket 2>&1 | Out-Null; $exists = ($LASTEXITCODE -eq 0) } catch { $exists = $false }
if (-not $exists) {
  if ($Region -eq "us-east-1") { AwsChecked s3api create-bucket --bucket $bucket }
  else { AwsChecked s3api create-bucket --bucket $bucket --region $Region --create-bucket-configuration "LocationConstraint=$Region" }
}
AwsChecked s3 cp $bundle "s3://$bucket/$key" --region $Region
$presigned = (& aws s3 presign "s3://$bucket/$key" --region $Region --expires-in 3600)
Write-Host "Uploaded + presigned (1h)." -ForegroundColor Green

# --- 3) security group ----------------------------------------------------
$vpc = (& aws ec2 describe-vpcs --region $Region --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
if (-not $vpc -or $vpc -eq "None") { throw "No default VPC in $Region. Create one (aws ec2 create-default-vpc) or use a custom subnet." }
$sgName = "$Tag-sg"
try { $sg = (& aws.exe ec2 describe-security-groups --region $Region --filters "Name=group-name,Values=$sgName" "Name=vpc-id,Values=$vpc" --query "SecurityGroups[0].GroupId" --output text 2>&1 | Select-Object -Last 1) } catch { $sg = "" }
if (-not $sg -or $sg -notmatch '^sg-') {
  $sg = (& aws ec2 create-security-group --region $Region --group-name $sgName --description "Memory Rhythm demo" --vpc-id $vpc --query GroupId --output text)
  AwsChecked ec2 authorize-security-group-ingress --region $Region --group-id $sg --protocol tcp --port 80 --cidr 0.0.0.0/0
  if ($KeyName) { AwsChecked ec2 authorize-security-group-ingress --region $Region --group-id $sg --protocol tcp --port 22 --cidr 0.0.0.0/0 }
}
Write-Host "Security group: $sg (vpc $vpc)" -ForegroundColor Green

# HTTPS needs 443 open for Caddy/TLS (idempotent — ignore "already exists").
if ($Https) {
  try { & aws.exe ec2 authorize-security-group-ingress --region $Region --group-id $sg --protocol tcp --port 443 --cidr 0.0.0.0/0 2>&1 | Out-Null } catch {}
}

# Resolve the nip.io hostname from the tagged Elastic IP (Caddy serves a real
# Let's Encrypt cert for "<eip-dashed>.nip.io" — no domain or account verification
# needed). The EIP is re-attached to this new instance in step 6b.
$nipHost = ""
if ($Https) {
  $eipIp = (& aws.exe ec2 describe-addresses --region $Region --filters "Name=tag:Name,Values=$Tag" --query "Addresses[0].PublicIp" --output text 2>&1 | Select-Object -Last 1)
  if (-not $eipIp -or $eipIp -notmatch '^\d+\.\d+\.\d+\.\d+$') {
    throw "-Https needs a tagged Elastic IP. Run a normal deploy once (it allocates + tags one), then re-run with -Https."
  }
  # Canonical dot form "<ip>.nip.io" — public resolvers (and thus Let's Encrypt)
  # return exactly the embedded IP, so the ACME HTTP-01 challenge hits us.
  $nipHost = "$eipIp.nip.io"
  Write-Host "HTTPS: Caddy + Let's Encrypt -> https://$nipHost (origin app on :8000)" -ForegroundColor Cyan
}

# --- 4) AMI (latest Ubuntu 24.04, has Python 3.12) via SSM public param ---
$ami = (& aws ssm get-parameters --region $Region --names "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id" --query "Parameters[0].Value" --output text)
if (-not $ami -or $ami -eq "None") { throw "Could not resolve Ubuntu 24.04 AMI in $Region." }
Write-Host "AMI: $ami (Ubuntu 24.04)" -ForegroundColor Green

# --- 5) user-data bootstrap ----------------------------------------------
# -Gemini drives ONLY the conversation LLM (두뇌+입) with real Gemini, keeping
# AI_PROVIDER=mock so STT/TTS/image/embedding stay offline-mock. This is the
# robust demo posture: the visible dialogue is real, but no Imagen access is
# required and no extra free-tier quota is spent on embeddings (memory: the
# free Gemini tier 429s after ~20 calls/day, then silently falls back to mock).
$aiProvider = "mock"
$geminiLine = ""
if ($Gemini) {
  $envFile = Join-Path $backend ".env"
  if (-not (Test-Path $envFile)) { throw "-Gemini set but backend/.env not found (needs GOOGLE_API_KEY)." }
  $keyLine = (Select-String -Path $envFile -Pattern '^\s*GOOGLE_API_KEY\s*=' | Select-Object -First 1).Line
  if (-not $keyLine) { throw "GOOGLE_API_KEY not found in backend/.env." }
  $apiKey = ($keyLine -replace '^\s*GOOGLE_API_KEY\s*=\s*', '').Trim().Trim('"')
  # Two systemd Environment lines: select Gemini for the LLM + inject the key.
  $geminiLine = "Environment=LLM_PROVIDER=google`nEnvironment=GOOGLE_API_KEY=$apiKey"
  Write-Host "  (Gemini LLM enabled; key injected via instance user-data)" -ForegroundColor Yellow
}

# -Eleven enables real ElevenLabs TTS (voice output). NOTE: a FREE ElevenLabs tier
# cannot use the standard "library" voices via the API (HTTP 402), so this only
# produces audio on a paid plan or with an owned/cloned voice (set ELEVENLABS_VOICE_ID).
$elevenLine = ""
if ($Eleven) {
  $envFile = Join-Path $backend ".env"
  if (-not (Test-Path $envFile)) { throw "-Eleven set but backend/.env not found (needs ELEVENLABS_API_KEY)." }
  function _EnvVal($name) {
    $line = (Select-String -Path $envFile -Pattern "^\s*$name\s*=" | Select-Object -First 1).Line
    if (-not $line) { return "" }
    return ($line -replace "^\s*$name\s*=\s*", '').Trim().Trim('"')
  }
  $elKey = _EnvVal 'ELEVENLABS_API_KEY'
  if (-not $elKey) { throw "ELEVENLABS_API_KEY not found in backend/.env." }
  $elevenLine = "Environment=TTS_PROVIDER=elevenlabs`nEnvironment=ELEVENLABS_API_KEY=$elKey"
  $elVoice = _EnvVal 'ELEVENLABS_VOICE_ID'; if ($elVoice) { $elevenLine += "`nEnvironment=ELEVENLABS_VOICE_ID=$elVoice" }
  $elModel = _EnvVal 'ELEVENLABS_MODEL'; if ($elModel) { $elevenLine += "`nEnvironment=ELEVENLABS_MODEL=$elModel" }
  Write-Host "  (ElevenLabs TTS enabled; key injected via instance user-data)" -ForegroundColor Yellow
}

# -Polly enables Amazon Polly TTS (Korean Seoyeon). The instance gets Polly access
# via an IAM instance role (no keys in env). We ensure the role/profile idempotently.
$pollyLine = ""
$iamProfileArg = @()
if ($Polly) {
  $roleName = "$Tag-role"; $profileName = "$Tag-profile"
  $haveRole = $true
  try { & aws.exe iam get-role --role-name $roleName 2>&1 | Out-Null; if ($LASTEXITCODE) { $haveRole = $false } } catch { $haveRole = $false }
  if (-not $haveRole) {
    $trustDoc = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    $tf = Join-Path $env:TEMP "mr-trust.json"; Set-Content -Path $tf -Value $trustDoc -Encoding ascii
    AwsChecked iam create-role --role-name $roleName --assume-role-policy-document "file://$tf"
  }
  $permDoc = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"polly:SynthesizeSpeech","Resource":"*"}]}'
  $pf = Join-Path $env:TEMP "mr-perm.json"; Set-Content -Path $pf -Value $permDoc -Encoding ascii
  AwsChecked iam put-role-policy --role-name $roleName --policy-name polly-tts --policy-document "file://$pf"
  $haveProfile = $true
  try { & aws.exe iam get-instance-profile --instance-profile-name $profileName 2>&1 | Out-Null; if ($LASTEXITCODE) { $haveProfile = $false } } catch { $haveProfile = $false }
  if (-not $haveProfile) {
    AwsChecked iam create-instance-profile --instance-profile-name $profileName
    AwsChecked iam add-role-to-instance-profile --instance-profile-name $profileName --role-name $roleName
    Start-Sleep -Seconds 12   # let the new instance profile propagate before run-instances
  }
  $iamProfileArg = @("--iam-instance-profile", "Name=$profileName")
  $pollyLine = "Environment=TTS_PROVIDER=polly`nEnvironment=POLLY_REGION=$Region"
  $envFile2 = Join-Path $backend ".env"
  if (Test-Path $envFile2) {
    $pv = (Select-String -Path $envFile2 -Pattern '^\s*POLLY_VOICE\s*=' | Select-Object -First 1).Line
    if ($pv) { $pvv = ($pv -replace '^\s*POLLY_VOICE\s*=\s*', '').Trim().Trim('"'); if ($pvv) { $pollyLine += "`nEnvironment=POLLY_VOICE=$pvv" } }
    $pe = (Select-String -Path $envFile2 -Pattern '^\s*POLLY_ENGINE\s*=' | Select-Object -First 1).Line
    if ($pe) { $pee = ($pe -replace '^\s*POLLY_ENGINE\s*=\s*', '').Trim().Trim('"'); if ($pee) { $pollyLine += "`nEnvironment=POLLY_ENGINE=$pee" } }
  }
  Write-Host "  (Polly TTS enabled; instance role $profileName grants polly:SynthesizeSpeech)" -ForegroundColor Yellow
}

$userData = @'
#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl
install -d /opt/app
curl -fsSL "__PRESIGNED__" -o /tmp/app.tar.gz
tar -xzf /tmp/app.tar.gz -C /opt/app
python3 -m venv /opt/app/venv
/opt/app/venv/bin/pip install --upgrade pip
/opt/app/venv/bin/pip install -r /opt/app/requirements.txt
# Seed the three demo personas (박순례/김철수/이영자) into SQLite so the AI leads
# recall with their REAL memories instead of inventing some. Offline (mock
# embeddings/images) — no API calls. Idempotent; never block boot on failure.
( cd /opt/app && STORE=sqlite /opt/app/venv/bin/python seed_demo.py ) || true
cat >/etc/systemd/system/memrhythm.service <<UNIT
[Unit]
Description=Memory Rhythm
After=network.target
[Service]
WorkingDirectory=/opt/app
Environment=AI_PROVIDER=__AIPROVIDER__
Environment=STORE=sqlite
__GEMINILINE__
__ELEVENLINE__
__POLLYLINE__
ExecStart=/opt/app/venv/bin/uvicorn app.main:app __UVICORNBIND__
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now memrhythm
__CADDYBLOCK__
'@
# With -Https the app listens only on localhost and Caddy terminates TLS in front
# of it (port 80 = ACME challenge + redirect, 443 = HTTPS) for the nip.io host.
$uvicornBind = if ($Https) { "--host 127.0.0.1 --port 8000" } else { "--host 0.0.0.0 --port 80" }
$caddyBlock = ""
if ($Https) {
  $caddyBlock = @"
# --- HTTPS via Caddy + Let's Encrypt (nip.io); never abort boot on a hiccup ---
set +e
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y
apt-get install -y caddy
cat >/etc/caddy/Caddyfile <<CADDY
$nipHost {
    reverse_proxy 127.0.0.1:8000
}
CADDY
systemctl enable caddy
systemctl restart caddy
"@
}
$userData = $userData.Replace("__PRESIGNED__", $presigned).Replace("__AIPROVIDER__", $aiProvider).Replace("__GEMINILINE__", $geminiLine).Replace("__ELEVENLINE__", $elevenLine).Replace("__POLLYLINE__", $pollyLine).Replace("__UVICORNBIND__", $uvicornBind).Replace("__CADDYBLOCK__", $caddyBlock)
$udFile = Join-Path $env:TEMP "memrhythm-userdata.sh"
Set-Content -Path $udFile -Value $userData -Encoding ascii -NoNewline

# --- 6) launch ------------------------------------------------------------
$keyArg = @(); if ($KeyName) { $keyArg = @("--key-name", $KeyName) }
$instId = (& aws ec2 run-instances --region $Region `
  --image-id $ami --instance-type $InstanceType --security-group-ids $sg `
  --associate-public-ip-address @keyArg @iamProfileArg `
  --user-data "file://$udFile" `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$Tag}]" `
  --query "Instances[0].InstanceId" --output text)
if ($LASTEXITCODE) { throw "run-instances failed." }
Write-Host "Launched instance: $instId" -ForegroundColor Green
Write-Host "Waiting for it to enter 'running'..." -ForegroundColor Cyan
AwsChecked ec2 wait instance-running --region $Region --instance-ids $instId

# --- 6b) re-attach the app's Elastic IP (if one exists) -------------------
# Keeps the public IP / URL stable across redeploys so a CloudFront origin or
# an nip.io hostname never has to be updated by hand. We look the EIP up by the
# same "$Tag" Name tag; associating it here auto-moves it off the old instance.
# Pass -NoEip to skip. If no tagged EIP exists, this is a no-op.
if (-not $NoEip) {
  $eipAlloc = (& aws ec2 describe-addresses --region $Region --filters "Name=tag:Name,Values=$Tag" --query "Addresses[0].AllocationId" --output text 2>&1 | Select-Object -Last 1)
  if ($eipAlloc -and $eipAlloc -match '^eipalloc-') {
    & aws ec2 associate-address --region $Region --instance-id $instId --allocation-id $eipAlloc --allow-reassociation *> $null
    if ($LASTEXITCODE) { Write-Host "  (warning: EIP $eipAlloc re-association failed; using the auto-assigned IP)" -ForegroundColor Yellow }
    else { Write-Host "Re-attached Elastic IP ($eipAlloc) -> $instId" -ForegroundColor Green }
  }
}

$dns = (& aws ec2 describe-instances --region $Region --instance-ids $instId --query "Reservations[0].Instances[0].PublicDnsName" --output text)
$ip = (& aws ec2 describe-instances --region $Region --instance-ids $instId --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host " Memory Rhythm is deploying. Bootstrap (apt + pip) takes ~2-4 min." -ForegroundColor Green
Write-Host ""
$primaryUrl = if ($Https) { "https://$nipHost/" } else { "http://$dns/" }
Write-Host "   URL:        $primaryUrl" -ForegroundColor White
if (-not $Https) { Write-Host "   IP:         http://$ip/" -ForegroundColor White }
if ($Https) { Write-Host "   (HTTP $ip redirects to HTTPS; cert issues ~30-90s after boot)" -ForegroundColor DarkGray }
$ttsMode = if ($Polly) { "Polly(ko)" } elseif ($Eleven) { "ElevenLabs" } else { "mock" }
$llmMode = if ($Gemini) { "Gemini" } else { "mock" }
Write-Host "   AI mode:    LLM=$llmMode, TTS=$ttsMode, STT/image/embedding=mock" -ForegroundColor White
Write-Host "   Instance:   $instId  ($InstanceType, $Region)" -ForegroundColor White
if ($KeyName) { Write-Host "   SSH:        ssh ubuntu@$dns  (logs: journalctl -u memrhythm -f)" -ForegroundColor DarkGray }
Write-Host ""
Write-Host " Poll readiness:  curl ${primaryUrl}api/health" -ForegroundColor DarkGray
Write-Host " Tear down:       pwsh deploy/destroy-aws.ps1 -Region $Region" -ForegroundColor DarkGray
Write-Host "==================================================================" -ForegroundColor Green
