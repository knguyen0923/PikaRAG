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
   should work -- see the new "Local LLM (Ollama + Tailscale)" section
   below for setup.

## 2. Server setup

```bash
ssh ubuntu@<instance-ip>
sudo apt update && sudo apt install -y python3.11 python3.11-venv git

sudo useradd -r -m -d /opt/pikarag -s /usr/sbin/nologin pikarag
sudo -u pikarag git clone <your-repo-url> /opt/pikarag
cd /opt/pikarag

sudo -u pikarag python3.11 -m venv .venv
sudo -u pikarag .venv/bin/pip install -r requirements.txt

sudo -u pikarag cp .env.example .env
sudo -u pikarag $EDITOR .env   # fill in DISCORD_TOKEN and LLM_HOST
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

## 3. Local LLM (Ollama + Tailscale)

Sets up the laptop that runs `/ask`'s language model, and connects it
privately to the Oracle Cloud instance -- no public IP, no port-forwarding.

**On the laptop (Windows):**

1. Install Tailscale: https://tailscale.com/download/windows, sign in,
   `tailscale up` (or use the tray app's "Connect" button).
2. Install Ollama: https://ollama.com/download/windows.
3. Pull the model: `ollama pull llama3.2:3b` (roughly 2GB download; Ollama
   runs as a background service afterward, listening on `localhost:11434`).
4. Find the laptop's Tailscale IP: `tailscale ip` (prints something like
   `100.64.1.2`). This is the value `LLM_HOST` needs, as `<that-ip>:11434`.
5. Keep the laptop powered on, plugged in, and connected whenever `/ask`
   should work -- Ollama does nothing until a request arrives, but it can't
   answer one if the machine is asleep or off.

**On the Oracle Cloud instance:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Both steps are outbound-only (Tailscale's coordination happens over HTTPS
out, same as the bot's existing Discord/PokeAPI/Pikalytics traffic) --
consistent with this instance's "no inbound ports needed" setup from
section 1.

Set `LLM_HOST` in `.env` (section 2 above) to the laptop's Tailscale IP
and port, e.g. `LLM_HOST=100.64.1.2:11434`.

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
