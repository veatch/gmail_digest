# Newsletter Digest Bot: Plan

## Goal

An AI agent that reads local-news newsletters, works out which editions are worth opening, and sends a short alert to **Telegram**. Jason then opens Gmail manually for anything that looks interesting. Over time the bot learns his interests from replies he sends it. It should run free or very cheaply.

It will be released as a **public project** that other people can clone and run themselves with as little setup as possible.

## Decisions so far

| Area | Decision |
|---|---|
| Language | **Python** |
| Hosting / scheduling | **GitHub Actions** daily cron |
| Distribution | **Public template repository**. Each user clicks "Use this template" to create their **own private copy** (not a fork) |
| State | Committed back to the user's own private copy using the built-in workflow token (no second repo, no personal access token) |
| Delivery | **Telegram bot** instead of email |
| Purpose | Newsletters already land in the main Gmail and often go unopened; the bot flags noteworthy editions rather than replacing them |
| Feedback loop | **Reply-to-update**: reply to the bot with likes and dislikes |
| Receiving replies | **Polling** (`getUpdates`) on each scheduled run, no webhook |
| Preference profile | Short plain-text file injected into every summarization prompt |
| Profile updates | LLM **rewrites** the profile (never appends); previous version goes to a dated **changelog** |
| Mail access (proposed) | **IMAP with an app password**: no Google Cloud project, no OAuth consent screen, no token expiry |

## Open questions

1. **Where does the bot read from?** The original idea used a sandboxed Gmail account, but the newsletters already arrive in the main Gmail. Options:
   - **Sandbox account, newsletters auto-forwarded to it.** Keeps the bot's credentials away from the main account. Needs a forwarding filter.
   - **Main Gmail, narrow access.** Simpler, but the app password gives IMAP access to the whole mailbox. The bot should only ever read, and only from a chosen label or sender list.

   The sandbox option is the safer default for a public project; the README can document both.
2. **Default LLM provider.** Make it configurable (Gemini free tier, Claude Haiku, or others) and pick one default for the quick-start.
3. **How "noteworthy" is decided.** Alert only when something clears a threshold, or always send a short daily digest?

## Pipeline

Each scheduled run:

1. **Poll Telegram** for messages since the last processed `update_id`. Accept only the configured chat ID.
2. **Update the profile** if there are new messages: LLM rewrites it; the old version goes to the changelog.
3. **Fetch new newsletters** over IMAP, read-only. Track processed message IDs in the state file rather than modifying the mailbox.
4. **Clean the content:** strip HTML, footers, and tracking links to save tokens.
5. **Summarize and rank** with the profile in the prompt.
6. **Send the alert** to Telegram (HTML parse mode; split if over 4096 characters).
7. **Commit state** (profile, changelog, `update_id`, processed IDs).

## Digest design

- **Tiers:** "Must read" (a few items, one line each), "Probably interesting," and a compressed "everything else" list.
- **Locator info:** newsletter name, subject line, and a "view in browser" link where available, so the edition is easy to find in Gmail.
- **"Why this is here"** note on non-obvious picks, so a wrong guess can be corrected with one reply.
- **Occasional wildcard** item outside stated interests, so the profile does not only narrow over time.
- **Telegram formatting:** HTML parse mode (only `<`, `>`, `&` need escaping), not MarkdownV2.
- Optional later: inline 👍/👎 buttons on each story, sent back as Telegram callbacks.

## Preference profile

- Keep it to a few hundred words.
- Sections: durable interests, durable dislikes, "currently following" (temporary topics that get pruned).
- On each update, the LLM gets the current profile plus the new feedback and returns a consolidated version.
- Changelog: one dated entry per revision so a bad rewrite can be reverted. Because state is committed to git, history is also preserved in the commit log.

## Security notes

- Newsletter content is **untrusted input**. The summarizer gets no tools and cannot act on instructions found in emails.
- The only trusted instruction channel is the configured Telegram chat ID. Messages from anyone else are ignored.
- The bot token, app password, and LLM key live in GitHub Secrets, never in the repo.
- The bot can only send to one hardcoded chat.
- If the token leaks, send `/revoke` to BotFather to rotate it.
- Use a **private** copy of the repo, since the profile and changelog are personal.

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
7. **Add GitHub secrets:** bot token, chat ID, Gmail address, app password, LLM key.
8. **Edit the config** (newsletter senders or label, schedule) and run the workflow manually once to test.

README note: keep the bot username private. The chat-ID check is the real protection, but there is no reason to advertise the bot.

## Proposed repo layout

```
newsletter-digest/
├── .github/workflows/digest.yml   # daily cron + manual dispatch, concurrency group
├── src/digest/
│   ├── main.py                    # orchestrates one run
│   ├── mail.py                    # IMAP fetch, processed-ID tracking
│   ├── clean.py                   # HTML to text, boilerplate stripping
│   ├── llm.py                     # provider-agnostic LLM calls
│   ├── telegram.py                # send, poll getUpdates, chat-ID check
│   ├── profile.py                 # load/rewrite profile, write changelog
│   └── prompts/
│       ├── digest.md
│       └── profile_update.md
├── state/
│   ├── profile.md
│   ├── changelog.md
│   └── state.json                 # update_id, processed message IDs
├── scripts/setup.py               # token to chat ID discovery and test message
├── config.example.yml
├── pyproject.toml
└── README.md
```

## Next steps

1. Resolve the open questions above (read location, default LLM, alert threshold).
2. Write the core modules: Telegram polling and chat-ID check, IMAP fetch and processed-ID tracking, HTML cleaning.
3. Write the two prompts: digest (tiers, "why this is here," wildcard) and profile rewrite.
4. Add the workflow file and the `setup` script.
5. Write the README with the setup steps above.
