# Free GCP `e2-micro` as a failover host

Run the tracker on your **Oracle** free VM as primary and a **Google Cloud
free `e2-micro`** as a hot standby, so alerts keep flowing if the primary dies —
without ever sending you a duplicate.

> **GCP Always Free:** one `e2-micro` (shared core, ~1 GB RAM) per month in
> `us-west1`, `us-central1`, or `us-east1`, plus 30 GB disk. That's enough for
> this agent. Deploying outside those regions is **not** free.

---

## How double-alerts are prevented

Each instance runs the same agent but coordinates via the
[`coordination`](../stock_tracker/coordination.py) layer. Two modes:

| Mode | Setup | Failover | Guarantee |
|---|---|---|---|
| **Role-based** (default) | `TRACKER_ROLE=primary` on Oracle, `TRACKER_ROLE=standby` on GCP | manual (promote standby) | standby is silent, so no duplicates |
| **Redis** (automatic) | set the same `REDIS_URL` on both | automatic within `LEASE_TTL`s | leader lease + per-event dedup key = exactly one alert |

Every alert is keyed by a content **fingerprint** (`signal.fingerprint()`), so
even during a leadership handover the shared dedup key lets only one host send.

---

## Option A — Role-based (simplest, no extra services)

**On the GCP box, configure it as standby:**

```bash
# in the repo's .env on the GCP instance
TRACKER_ROLE=standby
INSTANCE_ID=gcp-e2micro
# ... same Telegram/WhatsApp/source settings as primary ...
```

The standby runs the full pipeline (so it's warm) but **sends nothing**. If the
Oracle host goes down, promote the standby:

```bash
sed -i 's/^TRACKER_ROLE=.*/TRACKER_ROLE=primary/' .env
docker compose up -d            # picks up the new role
```

(Recovery is manual but trivial. Use Option B if you want it automatic.)

## Option B — Redis (automatic failover, zero duplicates active/active)

1. Create a **free Redis** (e.g. an Upstash free database) and copy its
   `rediss://…` URL.
2. Put the **same** `REDIS_URL` in `.env` on **both** hosts:
   ```bash
   REDIS_URL=rediss://default:<password>@<host>:<port>
   LEASE_TTL=30
   DEDUP_WINDOW=900
   ```
3. Start both. They elect a leader automatically; if the leader stops renewing
   its lease, the other promotes itself within `LEASE_TTL` seconds. The dedup
   key guarantees one alert per event regardless of timing.

`redis` is an optional dependency — it's only imported when `REDIS_URL` is set
(already in `requirements-tracker.txt`, installed in the Docker image).

---

## Create the GCP VM

1. <https://console.cloud.google.com> → **Compute Engine → Create instance**.
2. **Region:** `us-central1` (or `us-west1` / `us-east1`). **Machine type:**
   `e2-micro`. **Boot disk:** Ubuntu 24.04, ≤ 30 GB standard disk.
3. Create, note the external IP, then:

```bash
gcloud compute ssh <vm-name>      # or SSH from the console
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && sudo systemctl enable --now docker
# log out/in, then:
git clone <your-repo-url> && cd computational-finance
git checkout claude/stock-live-event-tracker-are7yq
cp .env.example .env && nano .env      # set TRACKER_ROLE=standby (or REDIS_URL)
docker compose up -d --build
docker compose logs -f tracker         # standby logs detections but won't alert
```

> The `e2-micro` has ~1 GB RAM, so keep `MEM_LIMIT` modest (e.g. `MEM_LIMIT=512m`).

---

## Verify it works

```bash
# On the standby, you should see processing but no external sends:
docker compose logs tracker | grep -i "suppressed by coordinator"

# Failover test (role mode): stop the primary, promote the standby:
#   primary$  docker compose down
#   standby$  sed -i 's/^TRACKER_ROLE=.*/TRACKER_ROLE=primary/' .env && docker compose up -d
```

### Caveats
- **Don't run two primaries** in role mode — that *is* how you get duplicates.
- One small instance each is plenty; respect source rate limits / ToS.
- Free `e2-micro` is tiny — fine for this agent, not for heavy add-ons like a
  local LLM or the Whisper audio relay (those want a GPU/bigger box).
