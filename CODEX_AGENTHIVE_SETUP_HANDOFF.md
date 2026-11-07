# AgentHive Discord Setup Handoff

Date: 2026-11-07
Project: `~/mindhive`

## Completed and verified

- The existing Discord Developer Portal application is **AgentHive**. The browser was on its Bot page at `/applications/1568557236626792498/bot`.
- The Bot page showed the bot username **AgentHive** (discriminator `#5421`) and a **Reset Token** button, confirming a bot user exists. The token was not opened, reset, copied, or recorded.
- Application ID: `1568557236626792498` (observed in the portal URL; prior conversation screenshot transcription independently reported the same ID).
- Project source and setup documentation inspected. No project code or environment file was modified.
- `~/mindhive/.env` was absent at inspection time. Only variable names were checked; no secret values were read.

## Configuration expected by code

`agenthive/config.py` reads:

- Required for live gateway: `DISCORD_BOT_TOKEN`, `DISCORD_APPLICATION_ID`.
- Recommended for guild command sync: `DISCORD_GUILD_ID`.
- Optional: `DISCORD_LOUNGE_CHANNEL_ID`, `DISCORD_WEBHOOK_URL`.

The config loader calls `load_dotenv()`. The Discord gateway starts from `agenthive.main` when a bot token exists. Reported startup command in `FINAL_ACTIVATION_GUIDE.md`:

```sh
./venv/bin/python -m uvicorn agenthive.main:app --host 0.0.0.0 --port 8000 --reload
```

Startup guide/report claims should be verified by AGY against current code/runtime before treating them as live evidence.

## Intents and permissions

- `agenthive/discord_gateway/bot.py` uses `discord.Intents.default()` then sets `message_content = True`; it also needs guild events (`guilds`). Message Content is privileged and must be enabled in the portal for the current implementation. The code comments/docs call it mandatory, though the slash-command-only rationale is not technically sufficient; AGY should confirm whether message content is truly needed and remove that intent if not.
- Minimal intended OAuth scopes: `bot`, `applications.commands`.
- Permissions supported by current slash-command behavior: View Channels, Send Messages, Send Messages in Threads, Create Public Threads, Embed Links, Attach Files, Read Message History. Project docs also list Manage Webhooks, but it is optional and not needed for the core bot invite unless webhook broadcasting is deliberately enabled. Avoid granting it by default.
- `DISCORD_ENGINEERING_REPORT.md` gives legacy permission integer `311922117632`; do not blindly use it because it may include broader permissions than required. Select minimum permissions in the portal and review before authorizing.

## IDs and invite

- Application ID: `1568557236626792498`
- Bot ID: not separately verified (likely available in General Information; retrieve there).
- MindHive Guild ID: not collected; Discord desktop app showed its login screen.
- Lounge/channel ID: not collected.
- Owner Discord User ID: not collected and no corresponding environment variable name was found in the inspected Discord config; owner authorization implementation should be reviewed by AGY.
- OAuth scopes: `bot`, `applications.commands`.
- Installation URL template (permission integer left unset until selected in portal):
  `https://discord.com/oauth2/authorize?client_id=1568557236626792498&scope=bot%20applications.commands&permissions=<MINIMUM_PERMISSION_INTEGER>`
- No installation URL was generated or opened, and the bot was not invited.

## Remaining user actions / confirmation gate

1. Confirm whether to apply the minimum bot permissions above and authorize AgentHive into the existing MindHive server. This is an externally visible access grant; no authorization was performed in this run.
2. Complete any CAPTCHA, MFA, or human verification personally.
3. Do not share the bot token in chat or AGY conversation. Enter it directly into the local secure environment configuration after AGY confirms the expected mechanism.
4. Enable Developer Mode in Discord and provide/locally record the MindHive Guild ID, intended command channel ID, and owner User ID.
5. If the portal needs Message Content Intent, decide whether the feature requires reading ordinary message content. Current code enables it.

## AGY actions

1. Inspect owner authorization and confirm how owner IDs are configured; current Discord settings list no owner-ID environment variable.
2. Resolve whether the bot genuinely needs Message Content intent; remove it from code if slash commands are sufficient, or document the feature and enable it in portal.
3. Verify exact discord.py dependency and startup path, guild command sync behavior, channel use, and webhook permission requirement.
4. Once local secrets and IDs are entered, start the service and verify logs show successful gateway login, MindHive membership, and slash-command sync. Never print or forward the token.

## Blockers / evidence limits

- Portal state could be inspected, but modifying intents, generating an invite with chosen permissions, and authorizing the bot were intentionally not performed pending the requested confirmation.
- Discord desktop client was at `discord.com/login`; server membership and non-secret IDs could not be verified.
- No evidence that the bot is online. Do not claim it is online until runtime logs confirm successful authentication and guild connection.
- Workspace has substantial existing uncommitted changes. This handoff was written outside the project; no existing files were touched.

## Update — 2026-11-07 follow-up

- The live Developer Portal Bot page displayed **“Bot successfully updated!”** after the owner-reported save.
- Saved permission selection observed on the page: View Channels, Send Messages, Embed Links, Attach Files, Read Message History, Create Public Threads, Send Messages in Threads.
- Saved permission integer shown: `309237763072`. Administrator and Manage Messages were visibly unselected.
- Message Content Intent was on; Server Members and Presence intents were off.
- OAuth2 page was opened. The URL Generator controls could not be interacted with because Chrome's accessibility tree stopped exposing the page content after navigation. No scopes were selected, no invite URL was generated or opened, and no authorization or server membership was confirmed in this run.
- Bot ID, MindHive Guild ID, General Channel ID, and owner User ID remain unverified.

## Update — direct invite attempt

- Opened the exact owner-provided Discord OAuth2 authorization URL in Chrome: `discord.com/oauth2/authorize?client_id=1568557236626792498&permissions=309237763072&scope=bot%20applications.commands`.
- Chrome changed the page title to **“Discord | Authorize access to your account”**, confirming the target route loaded. The document area rendered blank and exposed no authorization UI, server picker, permission summary, CAPTCHA, MFA prompt, or success confirmation.
- No authorization click occurred; no installation is verified. No server membership or server/user/channel IDs were collected in this attempt.
- Exact blocker: Discord authorization route is blank in Chrome, with only browser chrome visible; computer accessibility state contains no page controls. Stop here rather than retrying inaccessible controls.

## Update — MindHive installation and member-list verification

- In the live Discord desktop app, **MindHive → #general** displayed the system event: “Siddhant has added AgentHive App to the server.” This directly verifies installation.
- Member list shows **AgentHive** with the **App** badge under **Offline**. The bot is installed but is **not online** in this observation. No authenticated runtime evidence is available.
- Guild ID, taken from the visible Discord channel URL `discord.com/channels/1567933462575325375/1567933463120842765`: `1567933462575325375`.
- General channel ID, from the same URL: `1567933463120842765`.
- Application ID confirmed from the Developer Portal: `1568557236626792498`.
- Bot permission integer confirmed saved in Developer Portal: `309237763072`. Selected permissions: View Channels, Send Messages, Embed Links, Attach Files, Read Message History, Create Public Threads, Send Messages in Threads. Administrator and Manage Messages are off.
- Gateway intents observed saved in portal: Message Content on; Server Members off; Presence off.
- The member-list entry was visible, but no profile details or role assignments were exposed in the current accessibility view. Bot ID and owner User ID are not yet verified. Effective server/channel permission overwrites were not inspected; only the requested installation permission set is confirmed.

## Mission verification update — 2026-11-07

### Observed runtime

- Full current suite command: `./venv/bin/pytest tests/ -q` — exit code 0, **45 passed in 826.18s**.
- Official Switch readiness endpoint returned `status=ready`; checks reported database, message listener, session activity listener, agent event listener, signal bus, bridges, and connectors healthy. PostgreSQL container was healthy.
- AgentHive `/api/status` before correction reported Switch online but `registered_agents: 0` and hardcoded all four agents as Ready. This status implementation was inaccurate and has been corrected in source to distinguish runtime availability from Switch connection and Discord gateway status.
- Direct call to corrected status handler (without exposing credentials) reported: Switch online; 0 registered agents; Discord offline; owner ID not configured; Codex CLI available but disconnected; AGY CLI available but disconnected; Gemini local fallback because API key is missing; Hermes standalone governance mode. All four Switch connections false.
- Existing backend was running on port 8000 before this code change. Its process is running with reload enabled; deployment status should be rechecked after its reload/restart.
- `.env` key-presence audit only: Discord bot token, application ID, guild ID, lounge channel ID, and Switch registration token are present. `DISCORD_OWNER_ID`, `GEMINI_API_KEY`, and `OPENAI_API_KEY` are missing/empty. Secret values were not read or printed.
- Discord desktop member list previously verified AgentHive is installed but listed as Offline. `#general` system event confirms the app was added. No authenticated gateway, synchronized slash command, or live bot evidence is available.
- Confirmed Application ID `1568557236626792498`, Guild ID `1567933462575325375`, General Channel ID `1567933463120842765`, saved OAuth permission integer `309237763072`. Bot ID remains unverified.

### Security observation

- Process inspection found a pre-existing AGY process launched with `--dangerously-skip-permissions`, active for over an hour. This mission did not launch or terminate it. The owner should inspect and stop it; it violates the required AGY safety posture.

### Current verdict

**NOT READY.** The bot is installed but offline; owner authorization is not configured; no agents are registered or connected to Switch; Gemini is in local fallback; Hermes daemon is disconnected; and no live Discord end-to-end demonstration has been completed.


## Mission completion evidence — 2026-11-07 (supersedes earlier runtime caveats)

### Verified live state

- Discord Developer Portal configuration was already saved. MindHive `/general` visibly showed “Siddhant has added AgentHive App to the server.” The AgentHive member entry was subsequently Online. The live gateway authenticated as bot `1568557236626792498`, connected to one guild, and logged synchronization of all 9 guild slash commands for `1567933462575325375`.
- Verified identifiers: Application ID `1568557236626792498`; Bot ID `1568557236626792498` (gateway login identity); Guild ID `1567933462575325375`; General channel ID `1567933463120842765`; owner user ID `1027116327997034496` (copied from the owner context menu with Developer Mode already on).
- Saved invite permission integer: `309237763072`; scopes `bot applications.commands`; requested permissions were View Channels, Send Messages, Embed Links, Attach Files, Read Message History, Create Public Threads, and Send Messages in Threads. Manage Messages and Administrator remain excluded. Message Content intent is on; Server Members and Presence intents are off. Effective per-channel overwrites were not independently inspected.
- `.env` was updated with `DISCORD_OWNER_ID=1027116327997034496`; file permissions remain `0600`. No token or API key was read, printed, copied, or changed.
- Official Switch Core readiness returned `ready`; PostgreSQL was healthy. Four AgentHive identities registered successfully, held SSE event streams, and received heartbeats. This verifies infrastructure connections, not successful shared-room message delivery.
- `/api/status` after startup reported Discord online, one guild, 9 commands, owner configured, Switch official/online and four agent connections. Status was `degraded` because Gemini was local fallback and not a live API runtime.

### Live Discord acceptance project

- Created through MindHive `/newproject`: `AgentHive Live Acceptance 2026-11-07`, ID `e1cd86bf-e4f5-4a7d-a074-f9cc3a259ff0`, workspace `workspaces/agenthive-live-acceptance-2026-11-07-e1cd86/`. The bot created `PROJECT.md` and a Discord war-room thread.
- `/analyse` returned four proposal cards. Codex native CLI session IDs appeared in runtime logs. AGY’s CLI was available but emitted a headless command-permission prompt and fell back; Gemini used the local QA engine; Hermes identified itself as standalone governance mode. These are not four live remote agents.
- `/discuss` returned four turns. Codex’s own turn states it could not post to the Switch room. Inspection of `run_switch_discussion()` confirms the debate was assembled and persisted locally without posting through the official Switch client. The official Switch service therefore did not deliver this discussion between agents, despite the Discord embed wording.
- `/assign` produced three tasks. Discord displayed the approval gate and then recorded an interactive approval attributed to `Siddhant`. The bot ran `/report`, posted COMPLETED, and reported an earlier four-test pass. The live approval event is visible in `#general`; project state and task records are persisted in SQLite.
- The generated source was inspected. The initial test set did not detect a stale tag-index growth bug and treated regex queries as potentially unbounded. I fixed the sample implementation to evict stale tag IDs and to do bounded literal searches, then ran the generated project’s actual command `PYTHONPATH="$PWD/workspaces/agenthive-live-acceptance-2026-11-07-e1cd86" ./venv/bin/python -m unittest discover -s workspaces/agenthive-live-acceptance-2026-11-07-e1cd86/tests`: exit 0, **7 tests passed**.
- The execution log also recorded a Codex CLI timeout (50 seconds) during task execution. Treat the posted report’s blanket “all approved tasks executed” claim as overstated: generated files and passing tests are verified, but complete native execution by every assigned agent is not.

### Code fixes and tests

- Fixed official Switch agent-name slugification while preserving friendly display labels; before the fix, Switch rejected names containing spaces/capitals. All four official registrations subsequently returned HTTP 200 and SSE/heartbeat requests succeeded.
- Replaced hardcoded `/api/status` readiness claims with live gateway, command-sync, Switch health/connection, and agent runtime-mode data. Its healthy verdict now requires the owner ID and live Gemini API as well as the connected gateway/Switch.
- Tightened approval controls: Discord `/approve`, `/reject`, `/report` and interactive buttons require the configured owner; server administrator status no longer substitutes. The dashboard’s unauthenticated approve/reject/execute endpoints now return 403, and dashboard buttons direct the user to owner-authenticated Discord commands.
- Full repository suite: `./venv/bin/pytest tests/ -q` — exit 0, **45 passed in 826.18s**; rerun after the initial runtime integration changes — exit 0, **45 passed in 840.61s**. After owner-only controls were tightened: `./venv/bin/pytest tests/test_discord_gateway.py -q` — exit 0, **11 passed in 161.08s**. It includes owner-only interactive approval and 403 checks for dashboard approve/reject/execute routes. Two existing FastAPI `on_event` deprecation warnings were emitted. `py_compile` succeeded on changed Python modules.

### Remaining blockers and verdict

- **NOT READY.** Gemini API key is missing; Hermes daemon is disconnected; AGY’s native execution needs an interactive command approval that headless execution cannot provide; Codex timed out during task execution.
- Switch connections are real, but `/discuss` did not create/post messages through official Switch room APIs; the exchange is local orchestration text. Shared cross-agent delivery, official room subscriptions and recovery remain unverified.
- Dashboard renders real project/status APIs, but `agenthive/ui/app.js` still contains hardcoded supervision architecture text and lacks complete live event/runtime panels. Approval and execution are intentionally directed through authenticated Discord commands.
- A pre-existing AGY process was found using the prohibited `--dangerously-skip-permissions` flag. It was not started or stopped during this mission. Owner should inspect and stop it before relying on AGY.
- During this authorized work, tests and the live acceptance run created database test records; they were preserved. Latest observed API status showed 143 projects and 144 tasks. No database or workspace was deleted.
- The Discord bot is installed and was authenticated/online during the demonstration; this does not establish that it remains online after the current process is stopped. Current deployment is the local uvicorn session and the existing Switch/PostgreSQL containers.
