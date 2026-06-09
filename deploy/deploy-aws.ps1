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
  [string]$Tag = "memory-rhythm"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot          # repo root (deploy/ is one below)
$backend = Join-Path $repo "backend"

function Aws { param([Parameter(ValueFromRemainingArguments)]$a) & aws @a; if ($LASTEXITCODE) { throw "aws $($a -join ' ') failed ($LASTEXITCODE)" } }

# --- preflight ------------------------------------------------------------
& aws --version *> $null; if ($LASTEXITCODE) { throw "AWS CLI not installed. Install it, then run `aws configure`." }
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
& tar -czf $bundle -C $backend --exclude=".env" --exclude="__pycache__" --exclude="*.pyc" app static requirements.txt
if ($LASTEXITCODE) { throw "tar bundling failed." }
$sizeMB = [math]::Round((Get-Item $bundle).Length / 1MB, 2)
Write-Host "  bundle: $bundle ($sizeMB MB)" -ForegroundColor DarkGray

# --- 2) S3 upload + presign ----------------------------------------------
# Bucket name must be globally unique + lowercase. (account+region keep it stable-ish.)
$bucket = "memrhythm-deploy-$acct-$Region".ToLower()
$key = "deploy.tar.gz"
& aws s3api head-bucket --bucket $bucket 2>$null
$exists = ($LASTEXITCODE -eq 0)
if (-not $exists) {
  if ($Region -eq "us-east-1") { Aws s3api create-bucket --bucket $bucket }
  else { Aws s3api create-bucket --bucket $bucket --region $Region --create-bucket-configuration "LocationConstraint=$Region" }
}
Aws s3 cp $bundle "s3://$bucket/$key" --region $Region
$presigned = (& aws s3 presign "s3://$bucket/$key" --region $Region --expires-in 3600)
Write-Host "Uploaded + presigned (1h)." -ForegroundColor Green

# --- 3) security group ----------------------------------------------------
$vpc = (& aws ec2 describe-vpcs --region $Region --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
if (-not $vpc -or $vpc -eq "None") { throw "No default VPC in $Region. Create one (aws ec2 create-default-vpc) or use a custom subnet." }
$sgName = "$Tag-sg"
$sg = (& aws ec2 describe-security-groups --region $Region --filters "Name=group-name,Values=$sgName" "Name=vpc-id,Values=$vpc" --query "SecurityGroups[0].GroupId" --output text 2>$null)
if (-not $sg -or $sg -eq "None") {
  $sg = (& aws ec2 create-security-group --region $Region --group-name $sgName --description "Memory Rhythm demo" --vpc-id $vpc --query GroupId --output text)
  Aws ec2 authorize-security-group-ingress --region $Region --group-id $sg --protocol tcp --port 80 --cidr 0.0.0.0/0
  if ($KeyName) { Aws ec2 authorize-security-group-ingress --region $Region --group-id $sg --protocol tcp --port 22 --cidr 0.0.0.0/0 }
}
Write-Host "Security group: $sg (vpc $vpc)" -ForegroundColor Green

# --- 4) AMI (latest Ubuntu 24.04, has Python 3.12) via SSM public param ---
$ami = (& aws ssm get-parameters --region $Region --names "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id" --query "Parameters[0].Value" --output text)
if (-not $ami -or $ami -eq "None") { throw "Could not resolve Ubuntu 24.04 AMI in $Region." }
Write-Host "AMI: $ami (Ubuntu 24.04)" -ForegroundColor Green

# --- 5) user-data bootstrap ----------------------------------------------
$aiProvider = if ($Gemini) { "google" } else { "mock" }
$geminiLine = ""
if ($Gemini) {
  $envFile = Join-Path $backend ".env"
  if (-not (Test-Path $envFile)) { throw "-Gemini set but backend/.env not found (needs GOOGLE_API_KEY)." }
  $keyLine = (Select-String -Path $envFile -Pattern '^\s*GOOGLE_API_KEY\s*=' | Select-Object -First 1).Line
  if (-not $keyLine) { throw "GOOGLE_API_KEY not found in backend/.env." }
  $apiKey = ($keyLine -replace '^\s*GOOGLE_API_KEY\s*=\s*', '').Trim().Trim('"')
  $geminiLine = "Environment=GOOGLE_API_KEY=$apiKey"
  Write-Host "  (Gemini key will be injected via instance user-data)" -ForegroundColor Yellow
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
cat >/etc/systemd/system/memrhythm.service <<UNIT
[Unit]
Description=Memory Rhythm
After=network.target
[Service]
WorkingDirectory=/opt/app
Environment=AI_PROVIDER=__AIPROVIDER__
Environment=STORE=memory
__GEMINILINE__
ExecStart=/opt/app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now memrhythm
'@
$userData = $userData.Replace("__PRESIGNED__", $presigned).Replace("__AIPROVIDER__", $aiProvider).Replace("__GEMINILINE__", $geminiLine)
$udFile = Join-Path $env:TEMP "memrhythm-userdata.sh"
Set-Content -Path $udFile -Value $userData -Encoding ascii -NoNewline

# --- 6) launch ------------------------------------------------------------
$keyArg = @(); if ($KeyName) { $keyArg = @("--key-name", $KeyName) }
$instId = (& aws ec2 run-instances --region $Region `
  --image-id $ami --instance-type $InstanceType --security-group-ids $sg `
  --associate-public-ip-address @keyArg `
  --user-data "file://$udFile" `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$Tag}]" `
  --query "Instances[0].InstanceId" --output text)
if ($LASTEXITCODE) { throw "run-instances failed." }
Write-Host "Launched instance: $instId" -ForegroundColor Green
Write-Host "Waiting for it to enter 'running'..." -ForegroundColor Cyan
Aws ec2 wait instance-running --region $Region --instance-ids $instId
$dns = (& aws ec2 describe-instances --region $Region --instance-ids $instId --query "Reservations[0].Instances[0].PublicDnsName" --output text)
$ip = (& aws ec2 describe-instances --region $Region --instance-ids $instId --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host " Memory Rhythm is deploying. Bootstrap (apt + pip) takes ~2-4 min." -ForegroundColor Green
Write-Host ""
Write-Host "   URL:        http://$dns/" -ForegroundColor White
Write-Host "   IP:         http://$ip/" -ForegroundColor White
Write-Host "   AI mode:    $aiProvider" -ForegroundColor White
Write-Host "   Instance:   $instId  ($InstanceType, $Region)" -ForegroundColor White
if ($KeyName) { Write-Host "   SSH:        ssh ubuntu@$dns  (logs: journalctl -u memrhythm -f)" -ForegroundColor DarkGray }
Write-Host ""
Write-Host " Poll readiness:  curl http://$dns/api/health" -ForegroundColor DarkGray
Write-Host " Tear down:       pwsh deploy/destroy-aws.ps1 -Region $Region" -ForegroundColor DarkGray
Write-Host "==================================================================" -ForegroundColor Green
