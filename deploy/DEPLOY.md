# Deploying Memory Rhythm to AWS (single EC2 host)

The app is a FastAPI server that speaks **WebSocket** and keeps **in-memory
state**, so it needs a real always-on process — a single small EC2 instance is
the simplest fit. FastAPI also serves the built React frontend, so **one
instance = the whole app** (frontend + REST + WS, no CORS, no second service).

```
browser ──HTTP/WS──> EC2 :80  (uvicorn → FastAPI: static SPA + /api + /ws)
```

---

## What you do (once) — I can't do these for you

### 1. Install the AWS CLI
In the Claude prompt, run it with the `!` prefix so output lands here:

```
! winget install -e --id Amazon.AWSCLI
```
(or download the MSI: https://awscli.amazonaws.com/AWSCLIV2.msi). Reopen the
shell afterward so `aws` is on PATH.

### 2. Configure credentials
You need an IAM user/role access key with EC2 + S3 permissions.

```
! aws configure
```
Enter **Access Key ID**, **Secret Access Key**, default region
(e.g. `ap-northeast-2` for Seoul), and `json`.

Verify:
```
! aws sts get-caller-identity
```

---

## What I do — run the deploy

Once `aws configure` works, I run:

```
pwsh deploy/deploy-aws.ps1                 # mock AI — rock-solid, no secret, no 429
pwsh deploy/deploy-aws.ps1 -Gemini         # real Gemini (reads backend/.env key)
pwsh deploy/deploy-aws.ps1 -Region us-east-1 -KeyName my-keypair   # + SSH access
```

It bundles `backend/` (app + built frontend + requirements.txt), uploads to S3,
launches one **Ubuntu 24.04 / Python 3.12 / t3.micro** instance whose user-data
pip-installs and runs uvicorn on `:80` via systemd, then prints the public URL.

Bootstrap (apt + pip) takes ~2–4 min after launch. Poll:
```
curl http://<public-dns>/api/health
```

---

## Notes

- **Cost:** `t3.micro` is free-tier eligible (750 h/mo, 12 mo). S3 + egress are
  cents. **Tear down when done** so it stops billing:
  ```
  pwsh deploy/destroy-aws.ps1
  ```
- **AI mode:** default is **mock** — stable for an always-on public demo (the
  full UX works; responses are templated Korean). `-Gemini` uses the real model
  but the free-tier key 429s after ~20 calls/day, then silently falls back to
  mock. The key is injected via instance user-data (fine for a rotatable demo
  key; rotate it after).
- **HTTP, not HTTPS.** The demo serves plain `http://` (so `ws://`). Browser mic
  (Web Speech API) and some features prefer a secure origin; for `https://` you
  need an ALB + ACM cert or CloudFront — out of scope for this one-instance demo.
- **Region default:** whatever your `aws configure` region is. Seoul
  (`ap-northeast-2`) is closest for a Korean demo.
