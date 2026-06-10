<#
  destroy-aws.ps1 — tear down everything deploy-aws.ps1 created, so AWS stops
  billing. Terminates the tagged instance(s), deletes the security group, and
  empties + deletes the S3 deploy bucket.

  USAGE:  pwsh deploy/destroy-aws.ps1 [-Region us-east-1]
#>
[CmdletBinding()]
param(
  [string]$Region = "",
  [string]$Tag = "memory-rhythm"
)
$ErrorActionPreference = "Continue"
if (-not $Region) { $Region = (& aws configure get region) }
if (-not $Region) { throw "No region. Pass -Region or set one via `aws configure`." }
$acct = (& aws sts get-caller-identity --query Account --output text)
Write-Host "Tearing down '$Tag' in $Region (account $acct)..." -ForegroundColor Cyan

# 1) terminate tagged, non-terminated instances
$ids = (& aws ec2 describe-instances --region $Region `
  --filters "Name=tag:Name,Values=$Tag" "Name=instance-state-name,Values=pending,running,stopping,stopped" `
  --query "Reservations[].Instances[].InstanceId" --output text)
if ($ids -and $ids -ne "None") {
  $arr = $ids -split "\s+"
  Write-Host "Terminating: $($arr -join ', ')" -ForegroundColor Yellow
  & aws ec2 terminate-instances --region $Region --instance-ids $arr | Out-Null
  & aws ec2 wait instance-terminated --region $Region --instance-ids $arr
  Write-Host "Instances terminated." -ForegroundColor Green
} else {
  Write-Host "No running instances tagged '$Tag'." -ForegroundColor DarkGray
}

# 1b) release the tagged Elastic IP (an allocated-but-unassociated EIP is billed)
$eipAlloc = (& aws ec2 describe-addresses --region $Region --filters "Name=tag:Name,Values=$Tag" --query "Addresses[0].AllocationId" --output text 2>$null)
if ($eipAlloc -and $eipAlloc -match '^eipalloc-') {
  & aws ec2 release-address --region $Region --allocation-id $eipAlloc 2>$null
  if ($LASTEXITCODE -eq 0) { Write-Host "Released Elastic IP $eipAlloc." -ForegroundColor Green }
  else { Write-Host "Could not release EIP $eipAlloc (release manually if needed)." -ForegroundColor Yellow }
} else {
  Write-Host "No tagged Elastic IP to release." -ForegroundColor DarkGray
}

# 2) delete security group (retry: ENI detach lags briefly after termination)
$sg = (& aws ec2 describe-security-groups --region $Region --filters "Name=group-name,Values=$Tag-sg" --query "SecurityGroups[0].GroupId" --output text 2>$null)
if ($sg -and $sg -ne "None") {
  for ($i = 0; $i -lt 6; $i++) {
    & aws ec2 delete-security-group --region $Region --group-id $sg 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "Deleted security group $sg." -ForegroundColor Green; break }
    Start-Sleep -Seconds 10
  }
} else {
  Write-Host "No security group '$Tag-sg'." -ForegroundColor DarkGray
}

# 3) empty + delete the deploy bucket
$bucket = "memrhythm-deploy-$acct-$Region".ToLower()
& aws s3api head-bucket --bucket $bucket 2>$null
if ($LASTEXITCODE -eq 0) {
  & aws s3 rm "s3://$bucket" --recursive --region $Region | Out-Null
  & aws s3api delete-bucket --bucket $bucket --region $Region | Out-Null
  Write-Host "Deleted bucket $bucket." -ForegroundColor Green
} else {
  Write-Host "No deploy bucket to remove." -ForegroundColor DarkGray
}
Write-Host "Teardown complete." -ForegroundColor Green
