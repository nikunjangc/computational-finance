# Meta setup — Facebook Page + Instagram auto-posting

End-to-end setup so the tracker can post to your **Facebook Page** and
**Instagram** automatically. Plan ~30–60 min the first time; the Instagram app
permission is the only part that can take longer (review).

> What you'll end up with in `.env`:
> ```env
> PUBLISH_ENABLED=true
> PUBLISH_DRY_RUN=true            # keep true until you've eyeballed real posts
> FB_PAGE_ID=...
> FB_PAGE_ACCESS_TOKEN=...        # long-lived Page token
> IG_USER_ID=...                  # only for Instagram
> IMAGE_OUTPUT_DIR=/var/www/cards
> IMAGE_PUBLIC_BASE_URL=https://your-domain/cards
> ```

---

## 0. Prerequisites

- A **Facebook Page** you admin (create one at facebook.com/pages/create — a
  Page, not a personal profile).
- For Instagram: an Instagram **Business or Creator** account, **linked to that
  Page** (IG app → Settings → Account type → switch to Business/Creator, then
  link the Facebook Page).
- A Meta developer account: <https://developers.facebook.com> → *Get Started*.

---

## 1. Create a Meta app

1. <https://developers.facebook.com/apps> → **Create app**.
2. Use case: **Other** → type **Business**.
3. Name it (e.g. "Stock Event Poster"), create.
4. In the app dashboard, add the **Facebook Login** and (for IG) **Instagram
   Graph API** products if prompted. You mainly need the **Graph API Explorer**
   and permissions, below.

---

## 2. Get the IDs

**Facebook Page ID** (`FB_PAGE_ID`):
- Open your Page → **About** → scroll to *Page ID*, or use the Graph API
  Explorer (next step) with `GET /me/accounts` — each entry has an `id`.

**Instagram user ID** (`IG_USER_ID`, only if posting to IG):
- In Graph API Explorer: `GET /{page-id}?fields=instagram_business_account`
  → returns `instagram_business_account.id`. That id is your `IG_USER_ID`.

---

## 3. Get a long-lived Page access token

The token is what authorizes posting. Page tokens can be made long-lived (~60
days) and then effectively non-expiring once derived from a long-lived user
token.

1. Open the **Graph API Explorer**:
   <https://developers.facebook.com/tools/explorer>.
2. Select your app (top right).
3. **Add permissions** (Permissions dropdown):
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`   ← required to publish to the Page
   - For Instagram also add: `instagram_basic`, `instagram_content_publish`
4. Click **Generate Access Token**, approve. This is a short-lived **user**
   token — copy it.
5. **Exchange it for a long-lived user token** (run locally; replace the caps):

   ```bash
   curl -s "https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_LIVED_USER_TOKEN"
   ```
   (App ID/Secret are under **App settings → Basic**.) Copy the returned
   `access_token` (the long-lived user token).

6. **Get the long-lived Page token** from it:

   ```bash
   curl -s "https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_LIVED_USER_TOKEN"
   ```
   Find your Page in the list; its `access_token` is your **`FB_PAGE_ACCESS_TOKEN`**.
   Page tokens derived from a long-lived user token do not expire as long as the
   user token is valid and permissions aren't revoked.

> Keep this token secret — it can post as your Page. Put it only in `.env`
> (git-ignored), never in the repo.

---

## 4. Verify posting works (before automating)

Test the token by hand so you know it's good:

```bash
# Facebook text post
curl -s -X POST "https://graph.facebook.com/v21.0/FB_PAGE_ID/feed" \
  -d "message=Test from the stock tracker" \
  -d "access_token=FB_PAGE_ACCESS_TOKEN"
```

A JSON response with an `id` means success — check your Page. Delete the test
post manually.

---

## 5. (Instagram only) Host the image card publicly

Instagram fetches the post image from a **public URL** — it won't accept a file
upload. The agent writes the card to `IMAGE_OUTPUT_DIR`; you serve that folder at
`IMAGE_PUBLIC_BASE_URL`. On your Oracle VM (from `deploy/oracle-cloud.md`):

**Option A — quick nginx static serve**

```bash
sudo mkdir -p /var/www/cards
sudo chown "$USER" /var/www/cards
sudo apt-get install -y nginx
sudo tee /etc/nginx/sites-available/cards >/dev/null <<'NGINX'
server {
    listen 80;
    server_name your-domain-or-ip;
    location /cards/ { alias /var/www/cards/; autoindex off; }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/cards /etc/nginx/sites-enabled/cards
sudo nginx -t && sudo systemctl reload nginx
# Open port 80 in Oracle's security list / firewall for inbound web traffic.
```

Then:
```env
IMAGE_OUTPUT_DIR=/var/www/cards
IMAGE_PUBLIC_BASE_URL=http://your-domain-or-ip/cards
```

If you run the tracker in Docker, mount the host folder so the container writes
where nginx serves:
```yaml
# docker-compose.yml -> services.tracker
volumes:
  - /var/www/cards:/var/www/cards
```

**Option B — object storage / CDN.** Upload cards to S3/Cloudinary/Backblaze and
set `IMAGE_PUBLIC_BASE_URL` to that bucket's public base. (You'd add an uploader
step; the simplest path is Option A.)

> Instagram requires **HTTPS** in production. Put the VM behind Cloudflare or add
> a Let's Encrypt cert (`certbot`) so `IMAGE_PUBLIC_BASE_URL` is `https://`.
> Facebook-only posting does not need this (it uploads the file directly).

---

## 6. Turn it on

```env
PUBLISH_ENABLED=true
PUBLISH_DRY_RUN=true            # preview first
PUBLISH_MIN_CONFIDENCE=0.7
POST_IMAGE=true
FB_PAGE_ID=...
FB_PAGE_ACCESS_TOKEN=...
# Instagram:
IG_USER_ID=...
IMAGE_OUTPUT_DIR=/var/www/cards
IMAGE_PUBLIC_BASE_URL=https://your-domain/cards
```

1. Run with `PUBLISH_DRY_RUN=true` and watch the logs / console — you'll see the
   exact caption + image path it *would* post.
2. When happy, set `PUBLISH_DRY_RUN=false` and restart. Strong signals now post
   automatically to FB (and IG if configured).

```bash
docker compose up -d --build
docker compose logs -f tracker
```

---

## Permissions & review notes

- **Facebook Page posting** with `pages_manage_posts` generally works for Pages
  you admin without full App Review while your app is in *Development* mode and
  you're an admin/tester of the app.
- **Instagram content publishing** (`instagram_content_publish`) and using the
  app with accounts you don't own typically require **App Review** and Business
  Verification before it works in production. Add yourself as a tester to
  develop first.
- Respect **rate limits** (IG content publishing allows ~50 posts/24h per
  account) and each platform's automated-content and financial-content policies.
  A disclaimer is appended to every post; keep `PUBLISH_MIN_CONFIDENCE` high so
  you only post meaningful events.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `(#200) ...pages_manage_posts` error | Token missing the permission — regenerate with the scopes in step 3 |
| IG post skipped, FB works | `IMAGE_PUBLIC_BASE_URL` unset or the card URL isn't publicly reachable (check it loads in a browser) |
| IG `media` create fails with URL error | Image URL not HTTPS / not publicly accessible / wrong content-type |
| Token works then dies in ~1–2 months | You used a short-lived token — redo step 5 to derive the long-lived Page token |
| Nothing posts | `PUBLISH_DRY_RUN=true` (still previewing), or no signal cleared `PUBLISH_MIN_CONFIDENCE` |
