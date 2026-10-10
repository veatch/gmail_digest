# Newsletter Digest Bot: Plan

## Goal

An AI agent that reads local-news newsletters, works out which editions are worth opening, and sends a short alert to **Telegram**. Jason then opens Gmail manually for anything that looks interesting. Over time the bot learns his interests from replies he sends it. It should run free or very cheaply.

It will be released as a **public project** that other people can clone and run themselves with as little setup as possible.

## Decisions so far

| Area | Decision |
|---|---|
| Language | **Python** |
| Hosting / scheduling | **GitHub Actions** daily cron |
| Distribution | **Public template repository**. Each user clicks "Use this template" to create their **own private copy** (using template because a fork of a public repo cannot be private) |
| Template updates | The instance keeps a thin caller workflow and calls a reusable workflow in the public template repo. Application code can still use **opt-in path-scoped sync**; workflow files are not synced |
| State | Preference files committed back to the user's private copy with `GITHUB_TOKEN`. **Processed mail is not tracked in git** |
| Mail selection config | User-edited YAML (`config.yml`, from `config.example.yml`): named senders, inbox/label, lookback, **processed Gmail label**, upstream sync. Not rewritten by the bot |
| Senders | Each `mail.senders` entry has a human-facing **name** and a **from** address. A safe slug derived from the name identifies its state file; replies use the human-facing name. |
| Per-run LLM / Telegram | **One LLM call and one Telegram message per sender** that has new unlabeled mail. **No message when nothing is new** for that sender |
| Runtime state | Git-committed under `state/`: global `profile.md`, one file per sender, changelog, Telegram `update_id`. No processed-ID / subject / date ledger |
| Processed-mail tracking | Bot **adds a Gmail label** after a sender's new mail is successfully digested and sent. Next run searches for that sender **without** the label. Does not key off subject or send time |
| Mailbox writes | **Label only.** Do not delete, archive, or change read/unread. IMAP is read-write for that label STORE |
| Delivery | **Telegram bot** instead of email |
| Purpose | Newsletters already land in the main Gmail and often go unopened; the bot flags noteworthy editions rather than replacing them |
| Feedback loop | **Reply-to-update**: reply to the bot with likes and dislikes; name the sender to target its file, otherwise update the global profile |
| Receiving replies | **Polling** (`getUpdates`) on each scheduled run, no webhook |
| Preference profile | **Global** `state/profile.md` injected into **every** sender prompt, plus a **per-sender** state file for newsletter-specific memory |
| Profile updates | LLM **rewrites** the relevant file (never appends); previous version goes to a dated **changelog** |
| Mail access (proposed) | **IMAP with an app password**: no Google Cloud project, no OAuth consent screen, no token expiry |

## Open questions

1. **Where does the bot read from?** The original idea used a sandboxed Gmail account, but the newsletters already arrive in the main Gmail. Options:
   - **Sandbox account, newsletters auto-forwarded to it.** Keeps the bot's credentials away from the main account. Needs a forwarding filter.
   - **Main Gmail, narrow access.** Simpler, but the app password gives IMAP access to the whole mailbox. The bot should only search configured senders and only **write** the processed label.

   Labeling processed mail makes this sharper: a sandbox keeps the bot's write access off the main mailbox. The README should document both.
2. **Default LLM provider.** Make it configurable (Gemini free tier, Claude Haiku, or others) and pick one default for the quick-start.
3. ~~**How "noteworthy" is decided.**~~ **Decided:** if a sender has new unlabeled mail, always send that sender's digest (ranked inside the message). If they have nothing new, send nothing.

## Template updates (private copies)

"Use this template" creates an independent repo with **no upstream link**. Updates are a deliberate sync, not something GitHub wires up.

**Chosen approach:** keep workflow orchestration in a reusable workflow in the public template repo, called by the instance's small `.github/workflows/digest.yml`. The caller owns its schedule and forwards only the secrets the reusable workflow needs. Use `@main` while developing; switch to a release ref such as `@v1` once published.

The reusable workflow checks out the caller's private repository, so the app code, `config.yml`, and `state/` remain in that repository. Updating the reusable workflow does not require pushing a modified workflow file to the private repo. For user-owned repos, map required secrets by name rather than using `secrets: inherit`.

Application code can optionally auto-sync at the **start** of the reusable workflow:

- Config (`config.yml`):
  ```yaml
  upstream:
    auto_sync: true
    url: https://github.com/<org>/newsletter-digest.git
    ref: v0.3.0   # prefer release tags once stable; main is fine early on
  ```
- Sync is **path-scoped**, not a full merge. Checkout only app paths from upstream (e.g. `src/`, `scripts/`, `pyproject.toml`, `uv.lock`, shared prompts). Do not sync `.github/workflows/`; the caller workflow stays in the private repo and the reusable workflow is referenced directly from the template. **Never** overwrite `state/`, the user's `config.yml`, or secrets.
- The caller grants `contents: write` so the reusable workflow can push app and state commits with `GITHUB_TOKEN`. It does not need workflow-file write permission.
- Pin the reusable workflow to a release tag or SHA for stable behavior. Updating a floating major tag such as `v1` is a maintainer action; a caller pinned to an exact version tag must bump its `uses:` ref to upgrade.
- On sync failure or conflict: skip the upgrade, Telegram a short notice, and continue the digest on the current tree so a bad upstream cannot brick daily runs.
- Keep the workflow `concurrency` group so sync + state commits cannot race.

Document a manual fallback in the README (`git fetch` + same path checkout) for users who leave `auto_sync` off.

## Config shape (senders)

`mail.senders` is required (no “every message in the label” path). Each item has a human name and a From match:

```yaml
mail:
  label: INBOX
  processed_label: digest/processed   # Gmail label applied after a successful send
  lookback_days: 3                    # safety bound, not the uniqueness key
  max_messages: 20
  senders:
    - name: Axios
      from: newsletter@axios.com
    - name: Local Paper
      from: city@localpaper.com
```

- **`name`:** unique, case-insensitive human-facing label. Shown in digest headings and used in replies (`for Local Paper, …`). A lowercase underscore slug is derived from it for `state/senders/<slug>.md` (for example, `Local Paper` becomes `local_paper`). Derived slugs must be unique.
- **`from`:** case-insensitive substring match on the From header.

## Processed-mail tracking (Gmail label)

Do **not** record processed Message-IDs, subjects, or send times in git. Gmail is the ledger:

- Each run searches the configured folder for that sender’s mail that **does not** already have `mail.processed_label` (Gmail IMAP `X-GM-LABELS` / `-label:`).
- `lookback_days` only limits how far back unlabeled mail is considered, so a huge unlabeled backlog cannot blow a run.
- After that sender’s LLM call **and** Telegram send succeed, apply `processed_label` to those messages.
- If the LLM or Telegram fails, **leave the messages unlabeled** so the next run retries them.
- The bot never uses subject or Date as “already seen.” Replies, corrections, and duplicate subjects across days stay unambiguous.

## Pipeline

Each scheduled run:

1. **Optional upstream sync** (if `upstream.auto_sync`): fetch the configured ref, update allowlisted paths, commit and push if anything changed.
2. **Poll Telegram** for messages since the last processed `update_id`. Accept only the configured chat ID.
3. **Apply replies:**
   - If the text names a configured sender (`for Local Paper, …`, `Local Paper: …`, or similar), LLM-rewrite **that sender’s** state file.
   - Otherwise LLM-rewrite the **global** `profile.md`.
   - Previous version of the rewritten file goes to the changelog.
4. **For each sender in `config.yml` order**, independently:
   1. IMAP search: folder + From match + **not** `processed_label` + lookback + `max_messages`.
   2. If **no new messages: skip** LLM and Telegram for this sender (no “nothing new” ping).
   3. Fetch and **clean** bodies (HTML, footers, tracking links).
   4. **Build the prompt** from `prompts/digest.md` + **global profile** + **this sender’s state file** + the cleaned editions. Other senders’ mail and state are not included.
   5. **Call the configured LLM** once.
   6. **Send one Telegram message** for this sender (HTML parse mode; split if over 4096 characters). Include the configured **name** in the heading so replies can refer to that sender by name.
   7. **Apply `processed_label`** to the messages just handled.
5. **Commit state** (global profile, any changed sender files, changelog, `update_id`). Still no processed-mail list in git.

One sender’s LLM/Telegram/label failure must not drop the others. Commit whatever state succeeded. Label only the messages whose send succeeded.

## Digest design

- **One message per sender**, not a combined digest. Tiers and ranking apply **inside** that sender’s mail only.
- **Tiers:** "Must read" (a few items, one line each), "Probably interesting," and a compressed "everything else" list.
- **Locator info:** configured sender **name**, subject line, and a "view in browser" link where available, so the edition is easy to find in Gmail.
- **"Why this is here"** note on non-obvious picks, so a wrong guess can be corrected with one reply.
- **Occasional wildcard** item outside stated interests, so the profile does not only narrow over time.
- **Telegram formatting:** HTML parse mode (only `<`, `>`, `&` need escaping), not MarkdownV2.
- Optional later: inline 👍/👎 buttons on each story, sent back as Telegram callbacks.

## Preference profile (global + per sender)

- **`state/profile.md` (global):** tastes that apply across newsletters (“I don’t care about sports”). Injected into **every** sender prompt.
- **`state/senders/<slug>.md`:** memory for that newsletter only (“Axios: skip national politics; keep local housing”). The slug is derived from the configured sender name. Created empty/skeleton on first run if missing.
- Keep each file to a few hundred words. Sections: durable interests, durable dislikes, "currently following" (temporary topics that get pruned).
- On each update, the LLM gets the current file plus the new feedback and returns a consolidated version of **that file only**.
- Changelog: one dated entry per revision (`changelog/<date>-profile.md` or `changelog/<date>-<name>.md`) so a bad rewrite can be reverted. Git history is a second backup.

Telegram replies:

- `for Local Paper, ignore national news` → rewrite `state/senders/local_paper.md`.
- `I never want sports` (no sender name) → rewrite `state/profile.md`.
- Ignore unknown names; optionally the next digest can say the name wasn’t recognized (keep this quiet at first).

## Security notes

- Newsletter content is **untrusted input**. The summarizer gets no tools and cannot act on instructions found in emails.
- The only trusted instruction channel is the configured Telegram chat ID. Messages from anyone else are ignored.
- The bot token, app password, and LLM key live in **repository secrets** (Settings → Secrets and variables → Actions → Repository secrets), never in the repo. No GitHub Environment is required.
- The bot can only send to one hardcoded chat.
- If the token leaks, send `/revoke` to BotFather to rotate it.
- Use a **private** copy of the repo, since the profile, per-sender files, and changelog are personal.
- IMAP can apply one configured label. Document that clearly in the README (especially for main-Gmail users). The bot still must not delete mail or act on instructions found in newsletter bodies.

## Hosting options considered

### GitHub Actions (chosen)

- Standard 5-field cron under `on.schedule`; fastest interval is 5 minutes, so daily is no issue. Defaults to UTC, with an optional IANA `timezone:` field available since March 2026.
- Free for public repos; private repos get 2,000 free minutes per month, far more than a daily run needs.
- Scheduled runs can be delayed (sometimes 30+ minutes) under high load. Acceptable for a morning digest.
- Scheduled workflows are disabled in inactive repositories. Committing state each run counts as activity.
- Runners are ephemeral, so state is committed back to the repo.
- Use a workflow `concurrency` group so overlapping runs cannot clash on state commits.

### Cloudflare Workers (optional later)

- Telegram works easily (plain `fetch`). Gmail works via the REST API with an OAuth refresh token, but IMAP does not (it needs raw TCP).
- Free plan limits that matter: **10 ms CPU per cron trigger** (network wait time doesn't count, but HTML parsing and base64 decoding might), **50 subrequests per invocation**, 5 cron triggers per account, 100,000 requests/day. Cron wall time is up to 15 minutes.
- Natively JavaScript/TypeScript. Python Workers have been in open beta; current third-party package support should be verified before relying on them.
- Possible role: a Worker cron that dispatches the GitHub workflow for users who dislike Actions' timing.

### Other

- **A server already running:** plain cron, local files for state, no quotas. The user owns uptime and secrets.
- **Google Cloud Run jobs + Cloud Scheduler:** solid, but more setup than this needs.
- **Google Apps Script:** zero infrastructure and free Gmail access, but weaker HTML parsing, testing, and portability.

## Apps Script vs Python (earlier comparison)

| | **Google Apps Script** | **Python** |
|---|---|---|
| Cost | Free | Free on GitHub Actions for modest usage |
| Hosting | None, runs inside Google | GitHub Actions, a server, or Cloud Run |
| Gmail access | Built in, no OAuth setup | IMAP with an app password, or Gmail API with OAuth |
| Auth pitfalls | Minimal | OAuth tokens for "testing" apps expire after 7 days; IMAP avoids this |
| HTML cleanup | Hand-rolled, less convenient | `beautifulsoup4`, `selectolax`, `html2text`, `trafilatura` |
| State | Script Properties or a Drive file | Committed files in the repo |
| Testing / version control | Weak (`clasp` helps) | Native |
| Portability | Tied to Google | Runs anywhere |

**Why Python won:** better parsing libraries, real testing and git, easy for other people to clone, and IMAP works with the standard library alone.

## Language notes

- **Python:** best parsing ecosystem, first-class LLM SDKs, `uv` makes dependency handling fast in Actions.
- **JavaScript/TypeScript:** `cheerio` is equally capable; the natural choice only if going the Cloudflare Workers route.
- **Ruby:** Nokogiri is excellent, but LLM and Telegram tooling is thinner.
- **Go/Rust:** single binary is operationally neat, but far more code for no gain at this scale.
- Parsing matters less than it seems: the goal is mainly to cut tokens before the LLM call, and the model tolerates messy structure.

## New-user setup (target experience)

1. Click **Use this template** and create a **private** repo.
2. **Create a Telegram bot** with @BotFather: send `/newbot`, choose a name and a username ending in `bot`, and copy the token.
3. **Message your bot first** (e.g. `/start`). Bots cannot message a user who hasn't contacted them.
4. **Find your chat ID.** Ideally a `setup` script does this: paste the token, send your bot a message, and the script prints the ID and sends a test message. (Manual fallback: open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `message.chat.id`.)
5. **Create a Gmail app password** (requires 2-step verification) and enable IMAP.
6. **Get an LLM API key** from the chosen provider.
7. **Add repository secrets** (not environment secrets): bot token, chat ID, Gmail address, app password, LLM key.
8. **Copy `config.example.yml` → `config.yml`**, set named senders (`name` + `from`), inbox/label, `processed_label`, optional upstream sync; create the Gmail label if Gmail will not auto-create it; run the workflow manually once to test.

README note: keep the bot username private. The chat-ID check is the real protection, but there is no reason to advertise the bot. Also explain that template updates are opt-in sync, not automatic fork sync.

## Proposed repo layout

```
newsletter-digest/
├── .github/workflows/digest.yml   # caller: schedule, concurrency, permissions, secret mapping
├── .github/workflows/run.yml      # reusable implementation: checkout, sync, install, run
├── src/digest/
│   ├── main.py                    # orchestrates one run
│   ├── mail.py                    # IMAP fetch, unlabeled search, apply processed_label
│   ├── clean.py                   # HTML to text, boilerplate stripping
│   ├── llm.py                     # provider-agnostic LLM calls
│   ├── telegram.py                # send, poll getUpdates, chat-ID check
│   ├── profile.py                 # load/rewrite global + per-sender files, changelog
│   └── prompts/
│       ├── digest.md              # per-sender summarization (global + sender state)
│       └── profile_update.md
├── state/                         # personal; never overwritten by upstream sync
│   ├── profile.md                 # global tastes
│   ├── telegram.json              # getUpdates offset only
│   ├── changelog/                 # dated copies of rewritten files
│   └── senders/
│       ├── axios.md
│       └── localpaper.md
├── scripts/setup.py               # token to chat ID discovery and test message
├── config.example.yml             # named senders, labels, lookback, upstream sync
├── config.yml                     # user copy (gitignored or kept local to their private repo)
├── pyproject.toml
└── README.md
```

## Next steps

1. Resolve the open questions above (read location, default LLM, alert threshold).
2. ~~Sketch `config.example.yml` + opt-in path-scoped upstream sync in the workflow.~~
3. Next code slice: named senders in config + IMAP header fetch of **unlabeled** mail per sender → one Telegram list per sender that has mail (still no LLM); skip senders with nothing new; apply `processed_label` after send.
4. Then: commit `state/telegram.json` + skeleton per-sender files; no processed-ID ledger.
5. Core modules after that: Telegram polling and chat-ID check, HTML cleaning, per-sender LLM digest (global profile + sender state), reply routing by sender **name**.
6. Write the README with setup (including the processed Gmail label) and upgrade notes.
