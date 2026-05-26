# ControlPanel Kitchen — Linux Client Installer

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/sillymatter-mexico/controlpanel-kitchen-linux-client-installer/main/install.sh)
```

---

## What it does

1. **Authenticates** — Prompts for your ControlPanel Kitchen username, password, and a device name, obtains an API token, and saves it to `~/.cpk/credentials.json`. On subsequent runs the saved token is reused if it is still valid.
2. **Downloads the latest release** — Fetches the newest `python-linux-client` build from the CPK API and verifies its SHA-256 checksum.
3. **Installs the package** — Extracts the archive and installs the `cpk` CLI tool via [pipx](https://pipx.pypa.io) (isolated, no virtualenv management required).
4. **Applies database migrations** — Runs `cpk update migrate` to initialise or upgrade the local SQLite database.
5. **Installs systemd services** — Registers and starts the CPK agent as a systemd user service via `cpk agent install`.

The installer is self-updating: each run checks GitHub for a newer version of `install.sh` and re-executes itself automatically if one is found.

---

## Requirements

| Dependency | Notes |
|---|---|
| `curl` | Used to download the installer and release archive |
| `tar` | Used to extract the release archive |
| `python3` ≥ 3.12 | Runtime for the CPK client |
| `pipx` | Installed automatically if not present |

---

## After installation

```bash
cpk agent status     # check running services
cpk agent start      # start in dev / foreground mode
cpk auth login       # re-authenticate
cpk update check     # check for updates
```

Credentials are stored at `~/.cpk/credentials.json` (mode `0600`).
