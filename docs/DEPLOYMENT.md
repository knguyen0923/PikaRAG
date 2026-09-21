# Deploying PikaRAG

Target: an Oracle Cloud Free Tier ARM instance (per `pika-rag-project-plan.md`),
always-on, no cost. Any Ubuntu 22.04+ VPS works the same way if you go
elsewhere -- nothing below is Oracle-specific except the instance shape.

## 1. Accounts and secrets (needs you -- can't be automated)

1. **Discord bot token**: https://discord.com/developers/applications ->
   New Application -> Bot -> Reset Token. Also enable it under
   OAuth2 -> URL Generator (scope `bot`, permission `Send Messages` +
   `Use Slash Commands`) to get an invite link, and invite it to your server.
2. **Oracle Cloud instance**: console -> Compute -> Instances -> Create.
   - Shape: `VM.Standard.A1.Flex` (Ampere ARM, in the Always Free tier).
   - Image: Ubuntu 22.04 (ARM build).
   - Add your SSH public key at creation time.
   - Open port 443/80 only if you ever add a webhook listener -- this bot
     is outbound-only (Discord gateway + HTTPS calls out), so no inbound
     ports need opening for the bot itself.
3. **A dedicated laptop for local LLM inference** (8GB+ RAM; CPU-only is
   fine, just slower) that stays powered on and connected whenever `/ask`
   should work -- see the "Local LLM (Ollama + Tailscale)" section below
   for setup.

## 2. Server setup

```bash
ssh ubuntu@<instance-ip>
sudo apt update && sudo apt install -y python3.11 python3.11-venv git

sudo useradd -r -M -d /opt/pikarag -s /usr/sbin/nologin pikarag  # -M: don't
                                                                  # pre-populate the
                                                                  # home dir from
                                                                  # /etc/skel, or the
                                                                  # git clone below
                                                                  # fails on a
                                                                  # non-empty directory
sudo mkdir -p /opt/pikarag
sudo chown pikarag:pikarag /opt/pikarag
sudo -u pikarag git clone <your-repo-url> /opt/pikarag
cd /opt/pikarag

sudo -u pikarag python3.11 -m venv .venv
sudo -u pikarag .venv/bin/pip install -r requirements.txt

sudo -u pikarag cp .env.example .env
sudo -u pikarag $EDITOR .env   # fill in DISCORD_TOKEN; leave LLM_HOST blank
                                # for now -- section 3 below tells you what
                                # value goes there once the Ollama host is set up.
                                # Also set BOT_OWNER_ID to your own Discord
                                # user ID to enable the admin-only
                                # /debug-last and /llmstatus commands
                                # (optional -- if left unset, both commands
                                # are rejected for everyone). See
                                # .env.example's comment for how to find
                                # your user ID.
sudo chmod 600 /opt/pikarag/.env
```

Populate the data the bot reads at startup (`data/processed/`) by running
the two pipelines once, as the `pikarag` user:

```bash
sudo -u pikarag /opt/pikarag/.venv/bin/python -m pipeline.refresh_job
sudo -u pikarag /opt/pikarag/.venv/bin/python -m pipeline.refresh_pikalytics_job
```

Both are idempotent and safe to re-run; expect the Pikalytics one to take a
while the first time (one request per legal species, rate-limited fetch).

**Optional: conversational chat.** Set `CONVERSATION_CHANNEL_IDS` in
`.env` to let people talk to the bot in plain messages (no slash command)
in specific channels, instead of using `/analyze`. This requires enabling
Discord's privileged "Message Content Intent" for this bot first (Bot ->
Privileged Gateway Intents in the Developer Portal) -- the bot only
requests this intent when `CONVERSATION_CHANNEL_IDS` is set, but if you
enable the setting without enabling the portal toggle, Discord refuses
the connection outright and the bot fails to start. See
`docs/superpowers/specs/2026-09-21-conversational-chat-design.md` for the
full design.

## 3. Local LLM (Ollama + Tailscale)

Sets up the machine that runs `/ask`'s language model, and connects it
privately to the Oracle Cloud instance -- no public IP, no port-forwarding.

**Currently running on a MacBook** (`kenneths-macbook-pro`, Tailscale IP
`100.94.16.44`) -- the original plan to use a Windows laptop was dropped in
favor of this Mac, which was already set up for local development. Setup
performed there:

1. Install Tailscale (`brew install --cask tailscale`), sign in via the
   app's auth flow.
2. Ollama was already installed and had `qwen3.5:9b` pulled.
3. Ollama defaults to binding `localhost` only -- made it listen on all
   interfaces with `launchctl setenv OLLAMA_HOST "0.0.0.0"`, then fully
   killed and relaunched the Ollama app (quitting from the menu bar alone
   left the old process running; had to `kill` the `Ollama`/`ollama`
   processes directly and reopen the app). **Made permanent 2026-09-21**
   via a LaunchAgent (`~/Library/LaunchAgents/com.pikarag.ollama-env.plist`,
   not tracked in this repo -- it's local machine config, not project code):
   on every login it runs `launchctl setenv OLLAMA_HOST "0.0.0.0"`, then
   force-restarts Ollama so it actually picks up the setting (a login-item
   launch of Ollama that races ahead of this agent would otherwise still
   bind to `localhost`). Verified working: `launchctl load -w` triggers it
   immediately too, and it correctly restarted Ollama with `*:11434`
   listening. If this Mac is ever wiped/replaced, recreate the plist with
   `RunAtLoad=true` running that same command, then `launchctl load -w`
   it.
4. Get the Tailscale IP: `tailscale ip -4`. That's the value `LLM_HOST`
   needs, as `<that-ip>:11434`.
5. Keep this Mac powered on, awake, and connected whenever `/ask` should
   work -- Ollama does nothing until a request arrives, but it can't answer
   one if the machine is asleep or off.

**If switching back to a Windows laptop later,** it still needs from
scratch: Tailscale installed and signed in, Ollama installed
(https://ollama.com/download/windows), and `qwen3.5:9b` pulled
(`ollama pull qwen3.5:9b`, ~6.6GB) -- none of that has been done on any
Windows machine for this project.

**On the Oracle Cloud instance:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Both steps are outbound-only (Tailscale's coordination happens over HTTPS
out, same as the bot's existing Discord/PokeAPI/Pikalytics traffic) --
consistent with this instance's "no inbound ports needed" setup from
section 1.

Set `LLM_HOST` in `.env` (section 2 above) to the Ollama host's Tailscale
IP and port, e.g. `LLM_HOST=100.64.1.2:11434` (currently
`100.94.16.44:11434`, this MacBook).

**Turning the local LLM host on/off:** `scripts/llm_toggle.sh {on|off|status}`,
run on the Ollama host machine, brings Tailscale + Ollama up or down
together (Tailscale is toggled too since this project is the only thing
on this Mac that uses it). The live bot already degrades gracefully to an
offline message when this host is unreachable (`rag/circuit_breaker.py`),
so turning it off requires no other action anywhere -- useful for not
keeping this machine reachable/serving 24/7 when nobody's using `/ask`.

## 4. Install the systemd units

```bash
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo install -m 0440 deploy/sudoers-pikarag /etc/sudoers.d/pikarag
sudo visudo -cf /etc/sudoers.d/pikarag   # sanity-check the syntax before trusting it

sudo systemctl daemon-reload
sudo systemctl enable --now pikarag-bot.service
sudo systemctl enable --now pikarag-refresh-pokeapi.timer
sudo systemctl enable --now pikarag-refresh-pikalytics.timer
```

What each unit does:

| Unit | Cadence | Purpose |
|---|---|---|
| `pikarag-bot.service` | always-on | Runs the Discord bot itself; auto-restarts on crash. |
| `pikarag-refresh-pokeapi.timer` | weekly | Re-runs `pipeline.refresh_job` to pick up any newly-added species in `data/source`'s legal list. Restarts the bot on success only. |
| `pikarag-refresh-pikalytics.timer` | monthly | Clears `data/raw_pikalytics/` and re-runs `pipeline.refresh_pikalytics_job`, since that pipeline's own cache never expires on its own -- see `deploy/refresh-pikalytics-monthly.sh`. Restarts the bot on success only. |

Both refresh jobs validate their output before it goes live: each builds
its new data in memory, runs it through a schema/count check, and only then
swaps it into place over the existing file. If validation fails, the job
aborts -- the previous data is left in place untouched, the specific
problems are logged, and the job exits non-zero, so the systemd
`ExecStartPost` restart never fires and the bot keeps serving the last-known
good data instead of partial or corrupted output.

On every successful run, each job also writes its own last-successful-
refresh timestamp to `data/processed/.last_refresh_pokeapi.json` or
`data/processed/.last_refresh_pikalytics.json`. These files are gitignored
and purely informational (used to detect a stalled refresh) -- if you
notice them on disk, that's expected; they're safe to delete and will be
recreated on the next successful run.

Check status any time:

```bash
sudo systemctl status pikarag-bot.service
sudo journalctl -u pikarag-bot.service -f
sudo systemctl list-timers 'pikarag-*'
```

## 5. Regulation bumps (manual, judgment call)

When Pokemon Champions rotates to a new regulation:

1. Update `data/source`'s legal Pokemon list for the new regulation.
2. Re-verify `PIKALYTICS_FORMAT_CODE` in `pipeline/fetch_pikalytics.py`
   against Pikalytics' current format list (`https://www.pikalytics.com/llms.txt`
   lists supported formats under "Supported Formats"). The Pikalytics cache
   is nested by format code, so bumping it cannot silently serve stale data
   from the old regulation -- but confirming the *new* code is still a human
   call.
3. Run both refresh jobs manually once, then let the timers take over.

## 6. Updating the deployed code

```bash
cd /opt/pikarag
sudo -u pikarag git pull
sudo -u pikarag .venv/bin/pip install -r requirements.txt
sudo systemctl restart pikarag-bot.service
```
