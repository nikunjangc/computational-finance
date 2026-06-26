# X (Twitter) + LinkedIn auto-posting setup

Credentials for the two **text** publishers. No image hosting or app-review
image dance — but each platform needs a developer app and a write-scoped token.

> Ends up in `.env`:
> ```env
> X_API_KEY=...
> X_API_SECRET=...
> X_ACCESS_TOKEN=...
> X_ACCESS_SECRET=...
> LINKEDIN_ACCESS_TOKEN=...
> LINKEDIN_AUTHOR_URN=urn:li:person:XXXX
> ```
> Posting stays **dry-run** until `PUBLISH_DRY_RUN=false`.

---

## X / Twitter

The publisher posts via **API v2** (`POST /2/tweets`) using **OAuth 1.0a
user-context** credentials — the four keys below.

### 1. Get a developer account + app
1. <https://developer.x.com> → sign up for a developer account (the **Basic**
   tier is paid; the Free tier has very limited write access — check current
   limits before relying on it).
2. Create a **Project** and an **App** inside it.

### 2. Set app permissions to **Read and write**
- App → **Settings** → **User authentication settings** → set app permissions
  to **Read and write** (default is read-only). **Do this before generating
  tokens** — tokens minted while the app was read-only can't post.
- Set up User authentication (OAuth 1.0a); a callback URL is required by the
  form but isn't used for posting (any https URL works).

### 3. Copy the four credentials
App → **Keys and tokens**:
- **API Key** and **API Key Secret** → `X_API_KEY`, `X_API_SECRET`
- **Access Token** and **Access Token Secret** (generate them; make sure they
  show *Read and Write*) → `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`

### 4. Verify
```bash
# Quick sanity check that write works (uses your account):
curl -s -X POST "https://api.twitter.com/2/tweets" \
  -H "Content-Type: application/json" \
  --oauth2-bearer "" -d '{"text":"test"}' 2>/dev/null
```
> The cleanest test is just to run the tracker with these set and
> `PUBLISH_DRY_RUN=false` on a strong signal. A `403` usually means the app is
> still read-only or the tokens predate the permission change — regenerate them.

### Notes
- Posts auto-trim to **280 chars** (`tweet_text()`); images are not posted to X
  (v2 image upload is a separate v1.1 flow — out of scope here).
- Mind X's write rate limits on your tier.

---

## LinkedIn

The publisher posts via the **UGC Posts API** (`POST /v2/ugcPosts`) with a
bearer token scoped `w_member_social`, on behalf of an **author URN**.

### 1. Create an app
1. <https://www.linkedin.com/developers/apps> → **Create app** (you must
   associate it with a LinkedIn **Company Page** you admin).
2. **Products** tab → request **Share on LinkedIn** (gives `w_member_social`)
   and **Sign In with LinkedIn using OpenID Connect** (gives you your member id).

### 2. Get an access token with `w_member_social`
LinkedIn tokens are OAuth 2.0 (3-legged). Easiest path while developing:
- Use the developer console's **OAuth 2.0 Tools** → *Generate token* and select
  the `w_member_social` (and `openid profile`) scopes → copy the access token →
  `LINKEDIN_ACCESS_TOKEN`.
- These tokens expire (~60 days). For long-running use, implement the standard
  refresh-token exchange, or regenerate periodically.

### 3. Find your author URN
- **Member (personal):** call the userinfo endpoint with your token:
  ```bash
  curl -s -H "Authorization: Bearer LINKEDIN_ACCESS_TOKEN" \
    https://api.linkedin.com/v2/userinfo
  ```
  Use the returned `sub` value: `LINKEDIN_AUTHOR_URN=urn:li:person:<sub>`.
- **Company Page:** `LINKEDIN_AUTHOR_URN=urn:li:organization:<org-id>` (the org
  id is in your Page URL / admin view). Posting as an organization needs the
  app authorized for that Page and the `w_organization_social` product.

### 4. Verify
Run the tracker with the two vars set and `PUBLISH_DRY_RUN=false`; on a strong
signal it should create a public share. A `403`/`422` usually means the token
lacks `w_member_social` or the author URN doesn't match the token's owner.

### Notes
- LinkedIn posts the **full caption** (limit ~3000 chars), text only here.
- Keep `PUBLISH_MIN_CONFIDENCE` high so you only share meaningful events;
  every post carries the disclaimer.

---

## Turning it on (both)

```env
PUBLISH_ENABLED=true
PUBLISH_DRY_RUN=true        # preview first; flip to false to go live
PUBLISH_MIN_CONFIDENCE=0.7
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_SECRET=...
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_AUTHOR_URN=urn:li:person:XXXX
# optional: Telegram confirmation when a post goes live
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

X, LinkedIn, Facebook, and Instagram can all run live simultaneously — each is
gated by the same confidence threshold and dedup, so one event makes one set of
posts (no duplicates across your failover hosts).
