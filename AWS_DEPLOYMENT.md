# Avatar Demo — AWS Deployment

Complete description of the production deployment of the Avatar Demo app on AWS.

**Live URL:** https://ai-avatar.signosoft.com

---

## Architecture

```
Browser
  │
  │ HTTPS:443 (Let's Encrypt-style cert via AWS Certificate Manager,
  │            wildcard *.signosoft.com)
  ▼
Application Load Balancer (ai-avatar-lb)
  │
  │ HTTPS:443 (self-signed cert; ALB does not validate target certs)
  ▼
EC2 instance i-0732249cded0a4e10  (eu-central-1b)
  │
  │ Python uvicorn binds 0.0.0.0:443 directly with TLS
  ▼
FastAPI app (web_server.py)
  │
  ├── STT  (OpenAI Whisper)
  ├── LLM  (Echo, swappable)
  └── TTS  (Azure Neural + viseme stream)
```

The TLS that reaches the user is the ACM cert on the ALB — that's the public-trusted one. The internal hop from ALB to EC2 uses a self-signed cert, which is fine because ALBs do not validate target certificates by default.

---

## AWS Resources

### Region
`eu-central-1` (Frankfurt)

### EC2 Instance

| Property | Value |
|---|---|
| Instance ID | `i-0732249cded0a4e10` |
| Name tag | `ai-avatar-demo` |
| Instance type | `t3.micro` (Free Tier eligible: 2 vCPU, 1 GiB RAM, burstable) |
| AMI | Ubuntu Server 24.04 LTS (x86_64) |
| Storage | 10 GiB gp3 EBS, encrypted=false, deleteOnTermination=true |
| Availability Zone | `eu-central-1b` |
| Key pair | `SignoSoftFrankfurt` |
| Public IPv4 | (assigned at launch, stable while instance is not stopped) |
| Private IPv4 | `172.31.34.205` |
| SSH user | `ubuntu` |
| Credit specification | Standard (no surprise burst charges) |

**Security groups:**
- `sg-f0a1b29a` (default)
- `sg-013a2bb4274c4efd2` (internet) — allows inbound 22, 80, 443, 8080 from `0.0.0.0/0`

**Swap:** 2 GiB swapfile at `/swapfile`, persistent via `/etc/fstab`.

### Custom AMI

| Property | Value |
|---|---|
| Name | `ubuntu-avatar-base-v1` |
| Description | Ubuntu 24.04 + python3 + ffmpeg + pre-built venv at `/opt/avatar-venv` |
| Contents | OS deps, Python deps installed (no app code, no cert files) |

To launch a fresh instance from this AMI, rsync the `avatar-demo` folder, generate cert files (see below), and create the systemd unit.

### Application Load Balancer

| Property | Value |
|---|---|
| Name | `ai-avatar-lb` |
| Type | Application Load Balancer |
| Scheme | Internet-facing |
| TLS cert | AWS Certificate Manager wildcard `*.signosoft.com` |
| Listener | HTTPS:443 → forward to target group `ai-avatar` |

### Target Group

| Property | Value |
|---|---|
| Name | `ai-avatar` |
| Protocol : Port | HTTPS : 443 |
| Protocol version | HTTP/1 |
| Target type | Instance |
| Health check protocol | HTTPS |
| Health check path | `/` |
| Registered targets | `i-0732249cded0a4e10` on port 443 |

### Route 53

| Property | Value |
|---|---|
| Hosted zone | `signosoft.com` |
| Record | `ai-avatar.signosoft.com` (A / Alias) |
| Target | `ai-avatar-lb` Application Load Balancer |

---

## Server-Side Setup

### File system layout on EC2

```
/home/ubuntu/avatar-demo/        ← application code (rsynced from local)
  ├── web_server.py              ← FastAPI entrypoint
  ├── backend/                   ← Python pipeline modules + assets
  ├── static/                    ← index.html (Canvas frontend)
  ├── requirements.txt
  ├── requirements_web.txt
  └── .env                       ← API keys (OpenAI, Azure)

/opt/avatar-venv/                ← pre-built Python venv (baked into AMI)
  └── bin/uvicorn                ← server binary

/etc/ssl/avatar/                 ← self-signed cert for the ALB → EC2 hop
  ├── cert.pem                   (mode 644, owner ubuntu)
  └── key.pem                    (mode 600, owner ubuntu)

/etc/systemd/system/avatar-demo.service  ← systemd unit (see below)

/swapfile                        ← 2 GiB swap, mounted at boot via /etc/fstab
```

### systemd unit

`/etc/systemd/system/avatar-demo.service`:

```ini
[Unit]
Description=Avatar Demo
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/avatar-demo
Environment="PATH=/opt/avatar-venv/bin"
ExecStart=/opt/avatar-venv/bin/uvicorn web_server:app \
    --host 0.0.0.0 --port 443 \
    --ssl-keyfile /etc/ssl/avatar/key.pem \
    --ssl-certfile /etc/ssl/avatar/cert.pem
Restart=always
RestartSec=5
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
```

`AmbientCapabilities=CAP_NET_BIND_SERVICE` is what lets the unprivileged `ubuntu` user bind to the privileged port 443 (normally only root can use ports < 1024).

### Self-signed certificate

Generated once with:

```bash
sudo mkdir -p /etc/ssl/avatar
sudo openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /etc/ssl/avatar/key.pem \
  -out /etc/ssl/avatar/cert.pem \
  -days 3650 \
  -subj "/CN=avatar-demo"
sudo chown ubuntu:ubuntu /etc/ssl/avatar/*.pem
```

Valid for 10 years. The browser never sees this cert — only the ALB does, and ALBs don't validate target certs.

---

## Running the Server

### Day-to-day operation

The service is enabled in systemd, so it:
- Starts automatically on instance boot
- Restarts automatically on crash (`Restart=always`, 5-second delay)

You don't need to do anything to keep it running.

### Common commands

All run on the EC2 (SSH in first):

```bash
# SSH in (from your local machine)
ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem ubuntu@<EC2_PUBLIC_IP>

# Status
sudo systemctl status avatar-demo

# Restart (after code or cert changes)
sudo systemctl restart avatar-demo

# Stop / start
sudo systemctl stop avatar-demo
sudo systemctl start avatar-demo

# Live logs (Ctrl+C to exit)
sudo journalctl -u avatar-demo -f

# Last 50 log lines
sudo journalctl -u avatar-demo -n 50 --no-pager

# Verify the app is serving HTTPS locally
curl -k https://localhost/ | head -3
```

### Pushing code updates

This deployment is intentionally simple: **we rsync the working tree to the EC2 box**
and restart the systemd service.

#### Production target (current)

- **SSH host**: `ubuntu@ec2-63-180-232-181.eu-central-1.compute.amazonaws.com`
- **Deploy directory**: `/home/ubuntu/avatar-demo/`
- **systemd service**: `avatar-demo.service`
- **Python venv**: `/opt/avatar-venv/`

#### Update workflow (copy/paste)

##### 1) Build the frontend locally (recommended)

The FastAPI server (`web_server.py`) can serve a built Vite bundle from `frontend/dist/`.
When you change frontend code, build before uploading so the server has the latest assets.

From your local machine, in the project root:

```bash
# Build the React/Vite frontend (updates frontend/dist)
npm --prefix frontend run build
```

##### 2) Rsync the repo to EC2 (exclude secrets + local junk)

From your local machine, in the project root:

```bash
rsync -avz --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "myenv" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "frontend/node_modules" \
  --exclude "*.pem" \
  -e "ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem" \
  ./ ubuntu@ec2-63-180-232-181.eu-central-1.compute.amazonaws.com:/home/ubuntu/avatar-demo/
```

Notes:
- `--delete` makes the remote folder match your local tree (good for removing old files).
- `--exclude "*.pem"` prevents accidentally uploading private SSH keys to the server.
- The EC2 folder `/home/ubuntu/avatar-demo/` is **not** a git repo; rsync is the deploy mechanism.

##### 3) Restart the service (EC2)

SSH in:

```bash
ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem ubuntu@ec2-63-180-232-181.eu-central-1.compute.amazonaws.com
```

Then restart and check status:

```bash
sudo systemctl restart avatar-demo.service
sudo systemctl status avatar-demo.service --no-pager
```

##### 4) Verify locally on the EC2 instance

```bash
# Check the HTTPS listener works on localhost (self-signed)
curl -k -I https://127.0.0.1/

# Sanity-check a JSON API endpoint
curl -k https://127.0.0.1/api/personalities | head
```

##### 5) Confirm the new frontend bundle is present (optional but useful)

If you updated the frontend, confirm the built bundle exists and has fresh timestamps:

```bash
ls -la /home/ubuntu/avatar-demo/frontend/dist/ui-assets/
```

If you see the browser loading old `index-<hash>.js` files, it can be a caching issue.
In Safari, “Empty Caches” / private window usually resolves it.

##### 6) If you changed Python dependencies

If `requirements.txt` changed, install dependencies into the **existing venv**:

```bash
cd /home/ubuntu/avatar-demo
sudo /opt/avatar-venv/bin/pip install -r requirements.txt
sudo systemctl restart avatar-demo.service
```

If the service fails, inspect logs:

```bash
sudo journalctl -u avatar-demo.service -n 100 --no-pager
```

---

#### Legacy/alternate (generic) commands

From your local machine, in the project root:

```bash
# Sync code
rsync -avz -e "ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem" \
  --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
  --exclude='*.pyc' --exclude='output' \
  ./ ubuntu@<EC2_PUBLIC_IP>:~/avatar-demo/

# Restart service to pick up changes
ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem ubuntu@<EC2_PUBLIC_IP> \
  "sudo systemctl restart avatar-demo"
```

If you also added or removed Python dependencies, install them on the server:

```bash
ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem ubuntu@<EC2_PUBLIC_IP>
source /opt/avatar-venv/bin/activate
cd ~/avatar-demo
pip install --no-cache-dir -r requirements.txt
pip install --no-cache-dir -r requirements_web.txt
sudo systemctl restart avatar-demo
```

### Updating environment variables

API keys live in `/home/ubuntu/avatar-demo/.env`. To rotate:

```bash
scp -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem .env ubuntu@<EC2_PUBLIC_IP>:~/avatar-demo/
ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem ubuntu@<EC2_PUBLIC_IP> \
  "sudo systemctl restart avatar-demo"
```

---

## Cost

While running 24/7 in eu-central-1:

| Resource | Monthly cost (free tier) | Monthly cost (after free tier) |
|---|---|---|
| t3.micro instance | $0 | ~$8.76 |
| 10 GiB gp3 EBS | $0 (under 30 GB free) | ~$0.80 |
| Application Load Balancer | ~$16 | ~$16 |
| Route 53 hosted zone | (already paid for) | (already paid for) |
| Data transfer | negligible | negligible |
| **Total** | **~$16** (ALB only) | **~$25.50** |

The ALB is the dominant cost since it's not free-tier eligible.

---

## Troubleshooting

### Browser shows 502 Bad Gateway

The ALB can't reach a healthy target. Check in order:

1. **Is uvicorn running?**
   ```bash
   sudo systemctl status avatar-demo
   ```

2. **Is uvicorn responding to HTTPS locally?**
   ```bash
   curl -k https://localhost/ | head -3
   ```
   Should return HTML. If it returns "wrong version number", uvicorn is serving plain HTTP — the systemd unit is missing the `--ssl-keyfile`/`--ssl-certfile` flags.

3. **Is the target group target healthy?**
   AWS Console → EC2 → Target Groups → `ai-avatar` → Targets tab → Health status.

4. **Are the cert files present and readable by `ubuntu`?**
   ```bash
   ls -la /etc/ssl/avatar/
   ```
   `key.pem` should be `-rw------- ubuntu ubuntu`, `cert.pem` should be `-rw-r--r-- ubuntu ubuntu`.

### "Invalid HTTP request" warnings spam the journal

Expected if the target group is configured as HTTPS but uvicorn is serving plain HTTP — the ALB sends TLS handshake bytes and uvicorn tries to parse them as HTTP. Means the cert flags are missing from the systemd unit. Restart the service after fixing.

### Port 443 not bindable

```
[Errno 13] Permission denied
```

The systemd unit is missing `AmbientCapabilities=CAP_NET_BIND_SERVICE`. That capability is what lets the `ubuntu` user bind to port 443 without running the whole service as root.

### Service won't start

```bash
sudo journalctl -u avatar-demo -n 30 --no-pager
```

Common causes:
- `.env` file missing or has wrong API keys
- Cert file path wrong in the systemd unit
- Python import error (e.g., new dependency added but not installed in `/opt/avatar-venv`)

---

## Deploying a fresh instance from the AMI

If the current EC2 dies or you want a second instance:

1. **Launch instance from AMI** `ubuntu-avatar-base-v1` (in EC2 → AMIs)
2. Pick `t3.micro`, key `SignoSoftFrankfurt`, same security groups
3. SSH in:
   ```bash
   ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem ubuntu@<NEW_IP>
   ```
4. **Generate cert** (the AMI doesn't bake in `/etc/ssl/avatar/`):
   ```bash
   sudo mkdir -p /etc/ssl/avatar
   sudo openssl req -x509 -newkey rsa:2048 -nodes \
     -keyout /etc/ssl/avatar/key.pem \
     -out /etc/ssl/avatar/cert.pem \
     -days 3650 -subj "/CN=avatar-demo"
   sudo chown ubuntu:ubuntu /etc/ssl/avatar/*.pem
   ```
5. **Upload code and `.env`** from local:
   ```bash
   rsync -avz -e "ssh -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem" \
     --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
     ./ ubuntu@<NEW_IP>:~/avatar-demo/
   scp -i ~/.ssh/signosoft/SignoSoftFrankfurt.pem .env ubuntu@<NEW_IP>:~/avatar-demo/
   ```
6. **Create systemd unit** (paste the unit file from "systemd unit" section above):
   ```bash
   sudo tee /etc/systemd/system/avatar-demo.service > /dev/null <<'EOF'
   ... (see systemd unit section above)
   EOF
   sudo systemctl daemon-reload
   sudo systemctl enable --now avatar-demo
   ```
7. **Register the new instance** in the `ai-avatar` target group on port 443. Old instance can be deregistered or left.
