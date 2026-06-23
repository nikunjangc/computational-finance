# Deploying on an Oracle Cloud Free ARM VPS

The Oracle Cloud **Always Free** tier gives you an Ampere A1 (ARM64) VM — up
to 4 OCPU / 24 GB RAM at no cost — which is far more than this agent needs.
This guide takes you from zero to an always-on tracker.

> The Docker image is multi-arch, so it builds natively on ARM64.
> The agent only makes **outbound** connections (Telegram/WhatsApp, YouTube,
> CoinGecko), so **no inbound firewall ports are required**.

---

## 1. Create the VM

1. Sign up / log in at <https://cloud.oracle.com> and make sure you're in a
   region with ARM capacity (if "out of capacity", try another availability
   domain or region).
2. **Compute → Instances → Create Instance.**
   - **Image:** Canonical Ubuntu 24.04 (or 22.04).
   - **Shape:** *Ampere* → `VM.Standard.A1.Flex`. 1 OCPU / 6 GB RAM is plenty
     (you can use up to 4 OCPU / 24 GB free).
   - **SSH keys:** upload your public key (or let it generate one and save the
     private key).
3. Create it and note the **public IP**.

No ingress rules are needed (the app dials out only). Leave the default
security list as-is.

---

## 2. Connect and install Docker

```bash
ssh ubuntu@<PUBLIC_IP>

# Install Docker Engine + Compose plugin (official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu          # run docker without sudo
sudo systemctl enable --now docker      # start Docker on boot
# log out and back in so the group change takes effect
exit
ssh ubuntu@<PUBLIC_IP>
docker version                          # verify
```

---

## 3. Get the code onto the VM

Pick whichever is easiest:

**A. Clone from GitHub** (repo is private → use a Personal Access Token or a
deploy key):

```bash
git clone https://github.com/nikunjangc/computational-finance.git
cd computational-finance
git checkout claude/stock-live-event-tracker-are7yq
```

**B. Or copy just what you need from your laptop:**

```bash
# from your local machine
scp -r computational-finance ubuntu@<PUBLIC_IP>:~/
```

---

## 4. Configure secrets

```bash
cp .env.example .env
nano .env        # fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, YOUTUBE_CHANNELS, etc.
```

`.env` is git-ignored — your tokens never leave the VM.

---

## 5. Start it

```bash
docker compose up -d --build      # build for ARM64 and run in the background
docker compose logs -f tracker    # watch alerts stream in; Ctrl-C to stop watching
```

`restart: unless-stopped` (in `docker-compose.yml`) plus Docker being enabled
on boot means the agent comes back automatically after a crash **or a VM
reboot**. For most people that's all you need — you can stop here.

---

## 6. (Optional) Belt-and-suspenders: systemd unit

If you want systemd to explicitly own the lifecycle (nice logs via
`journalctl`, guaranteed start order), install the provided unit:

```bash
sudo cp deploy/stock-tracker.service /etc/systemd/system/
# edit the WorkingDirectory in the file if your path isn't /home/ubuntu/computational-finance
sudo systemctl daemon-reload
sudo systemctl enable --now stock-tracker
sudo systemctl status stock-tracker
journalctl -u stock-tracker -f
```

---

## Staying inside the free tier (≤ 4 OCPU / ≤ 24 GB)

There are **two independent limits** — use both:

1. **VM shape = the billing guardrail.** When you create the `A1.Flex`
   instance, set it to at most **4 OCPU / 24 GB**. Oracle will not let the VM
   exceed its shape, so you cannot accidentally drift into paid territory. This
   is the limit that actually protects your bill — Docker cannot.
2. **Container cap = a safety net** (in `docker-compose.yml`, tunable via
   `.env`):
   ```env
   CPU_LIMIT=1.0     # throttle: cgroups cap CPU share (no "fail" on CPU)
   MEM_LIMIT=1g      # hard fail: container is OOM-killed if it exceeds this,
                     #            then auto-restarted by restart: unless-stopped
   MEM_RESERVE=128m
   ```
   The agent normally uses **< 0.5 CPU / < 200 MB**, so the defaults leave huge
   headroom while still capping a runaway. To pin the container to the full
   free-tier ceiling instead, set `CPU_LIMIT=4.0` and `MEM_LIMIT=24g` (never
   set `MEM_LIMIT` above your VM's actual RAM).

   Verify the effective limits before starting:
   ```bash
   docker compose config | grep -iE "cpus|memory"
   docker stats stock-tracker          # live CPU/MEM usage once running
   ```

## Day-2 operations

```bash
# Update to the latest code
git pull && docker compose up -d --build

# Tail logs / confirm the heartbeat (logged every 5 min)
docker compose logs -f tracker

# Restart / stop
docker compose restart tracker
docker compose down

# Quick offline self-test inside the image
docker compose run --rm tracker --demo
```

### Notes
- **Keep it small:** one instance is the right size. Don't fan out into many
  pollers — respect YouTube / exchange rate limits and Terms of Service.
- **Cost:** staying within the Always Free shape (≤4 OCPU / ≤24 GB ARM, ≤200 GB
  block storage) means no charges. Oracle may reclaim *idle* Always-Free VMs;
  a continuously-running agent like this keeps it active.
- **Security:** keep the box patched (`sudo apt update && sudo apt upgrade`),
  use SSH keys only, and never commit your `.env`.
