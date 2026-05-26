#!/usr/bin/env bash
# install.sh — Public installer for the ControlPanel Kitchen Linux Client
#
# Usage:  bash install.sh
#
# What this script does:
#   1. Prompts for username, password and device name.
#   2. Authenticates against the CPK API and obtains an API token.
#   3. Saves the token and device name to ~/.cpk/credentials.json (mode 0600).
#   4. Fetches the latest python-linux-client deploy metadata from the API.
#   5. Downloads the release archive and verifies its SHA-256 checksum (if provided).
#   6. Extracts the archive to a temporary directory.
#   7. Runs `make install` inside the extracted release directory.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

readonly CPK_API="https://api.controlpanel.kitchen"
readonly CPK_APP_NAME="python-linux-client"
readonly CPK_CREDENTIALS_DIR="${HOME}/.cpk"
readonly CPK_CREDENTIALS_FILE="${CPK_CREDENTIALS_DIR}/credentials.json"
readonly CPK_INSTALLER_URL="https://raw.githubusercontent.com/sillymatter-mexico/controlpanel-kitchen-linux-client-installer/main/install.sh"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_info()  { printf '\033[0;32m[cpk]\033[0m %s\n' "$*"; }
_warn()  { printf '\033[0;33m[cpk]\033[0m %s\n' "$*" >&2; }
_error() { printf '\033[0;31m[cpk]\033[0m ERROR: %s\n' "$*" >&2; }
_die()   { _error "$*"; exit 1; }

# Check for a required command and exit with a helpful message if missing.
_require() {
    local cmd="$1"
    command -v "$cmd" >/dev/null 2>&1 || _die "Required command not found: '$cmd'. Please install it and re-run."
}

# Portable JSON field extractor — uses python3 (always available on target systems).
_json_field() {
    local json="$1" field="$2"
    python3 -c "
import sys, json
data = json.loads(sys.argv[1])
val = data.get(sys.argv[2])
if val is None:
    sys.exit(1)
print(val)
" "$json" "$field"
}

# ---------------------------------------------------------------------------
# Self-update
# ---------------------------------------------------------------------------

_SELF="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/$(basename "$0")"

if [[ -f "${_SELF}" ]] && command -v curl >/dev/null 2>&1; then
    _UPDATE_TMP=$(mktemp)
    if curl -fsSL -o "${_UPDATE_TMP}" "${CPK_INSTALLER_URL}" 2>/dev/null; then
        if ! cmp -s "${_SELF}" "${_UPDATE_TMP}"; then
            _info "Installer update available — applying…"
            chmod +x "${_UPDATE_TMP}"
            cp "${_UPDATE_TMP}" "${_SELF}"
            rm -f "${_UPDATE_TMP}"
            _info "Update applied. Re-running…"
            exec "${_SELF}" "$@"
        fi
    else
        _warn "Could not check for installer updates (continuing with current version)."
    fi
    rm -f "${_UPDATE_TMP}"
fi

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

_require curl
_require make
_require tar
_require python3

# ---------------------------------------------------------------------------
# Check for an existing valid token
# ---------------------------------------------------------------------------

TOKEN=""
CPK_DEVICE_NAME=""

if [[ -f "${CPK_CREDENTIALS_FILE}" ]]; then
    _SAVED_TOKEN=$(python3 -c "
import sys, json
try:
    data = json.load(open(sys.argv[1]))
    print(data.get('token', ''))
except Exception:
    print('')
" "${CPK_CREDENTIALS_FILE}")
    _SAVED_DEVICE=$(python3 -c "
import sys, json
try:
    data = json.load(open(sys.argv[1]))
    print(data.get('device_name', ''))
except Exception:
    print('')
" "${CPK_CREDENTIALS_FILE}")

    if [[ -n "${_SAVED_TOKEN}" ]]; then
        _info "Found existing token, verifying…"
        _ME_HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
            -H "Authorization: ${_SAVED_TOKEN}" \
            "${CPK_API}/api/auth/me/" || echo "000")
        if [[ "${_ME_HTTP_CODE}" == "200" ]]; then
            _info "Token is valid — skipping login."
            TOKEN="${_SAVED_TOKEN}"
            CPK_DEVICE_NAME="${_SAVED_DEVICE}"
        else
            _warn "Existing token invalid (HTTP ${_ME_HTTP_CODE}) — re-authenticating…"
        fi
    fi
fi

if [[ -z "${TOKEN}" ]]; then

# ---------------------------------------------------------------------------
# Collect credentials from the user
# ---------------------------------------------------------------------------

printf '\n\033[1mControlPanel Kitchen — Linux Client Installer\033[0m\n\n'

read -r -p "Username: " CPK_USERNAME
[[ -n "${CPK_USERNAME}" ]] || _die "Username cannot be empty."

read -r -s -p "Password: " CPK_PASSWORD
printf '\n'
[[ -n "${CPK_PASSWORD}" ]] || _die "Password cannot be empty."

read -r -p "Device name (identifies this machine): " CPK_DEVICE_NAME
[[ -n "${CPK_DEVICE_NAME}" ]] || _die "Device name cannot be empty."

# ---------------------------------------------------------------------------
# Authenticate and obtain an API token
# ---------------------------------------------------------------------------

_info "Authenticating as '${CPK_USERNAME}'…"

LOGIN_BODY=$(python3 -c "
import json, sys
print(json.dumps({'username': sys.argv[1], 'password': sys.argv[2]}))
" "${CPK_USERNAME}" "${CPK_PASSWORD}")

LOGIN_RESPONSE=$(
    curl -s -f \
        -X POST \
        -H "Content-Type: application/json" \
        -d "${LOGIN_BODY}" \
        "${CPK_API}/api/auth/login/" \
) || _die "Login request failed. Check your username and password."

TOKEN=$(
    python3 -c "
import sys, json
data = json.loads(sys.argv[1])
token = data.get('token')
if not token:
    print('ERROR: no token in response', file=sys.stderr)
    sys.exit(1)
# Normalise to 'Token <key>' format, matching the SDK convention.
if not token.startswith('Token '):
    token = 'Token ' + token
print(token)
" "${LOGIN_RESPONSE}"
) || _die "Could not extract token from login response."

_info "Login successful."

# ---------------------------------------------------------------------------
# Save credentials  (~/.cpk/credentials.json)
# Mirrors _save_credentials() in cli/commands/auth.py
# ---------------------------------------------------------------------------

mkdir -p "${CPK_CREDENTIALS_DIR}"

# Preserve any existing keys (e.g. admin_token) and merge new values on top.
if [[ -f "${CPK_CREDENTIALS_FILE}" ]]; then
    EXISTING_JSON=$(<"${CPK_CREDENTIALS_FILE}")
else
    EXISTING_JSON="{}"
fi

MERGED_JSON=$(
    python3 -c "
import sys, json
existing = json.loads(sys.argv[1])
existing['token']       = sys.argv[2]
existing['device_name'] = sys.argv[3]
print(json.dumps(existing))
" "${EXISTING_JSON}" "${TOKEN}" "${CPK_DEVICE_NAME}"
)

printf '%s' "${MERGED_JSON}" > "${CPK_CREDENTIALS_FILE}"
chmod 600 "${CPK_CREDENTIALS_FILE}"

_info "Credentials saved to ${CPK_CREDENTIALS_FILE}"

fi  # end: if [[ -z "${TOKEN}" ]]

# ---------------------------------------------------------------------------
# Fetch latest deploy metadata
# ---------------------------------------------------------------------------

_info "Fetching latest '${CPK_APP_NAME}' deploy metadata…"

DEPLOY_RESPONSE=$(
    curl -s -w '\n%{http_code}' \
        -H "Authorization: ${TOKEN}" \
        "${CPK_API}/api/server/client-deploys/${CPK_APP_NAME}/latest/"
)
DEPLOY_HTTP_CODE=$(printf '%s' "${DEPLOY_RESPONSE}" | tail -n1)
DEPLOY_JSON=$(printf '%s' "${DEPLOY_RESPONSE}" | head -n -1)

if [[ "${DEPLOY_HTTP_CODE}" != "200" ]]; then
    _die "Could not fetch deploy metadata (HTTP ${DEPLOY_HTTP_CODE}): ${DEPLOY_JSON}"
fi

DEPLOY_VERSION=$(
    python3 -c "
import sys, json
data = json.loads(sys.argv[1])
print(data.get('version', '(unknown)'))
" "${DEPLOY_JSON}"
)

DEPLOY_UUID=$(
    python3 -c "
import sys, json
data = json.loads(sys.argv[1])
uuid = data.get('uuid')
if not uuid:
    print('ERROR: no uuid in deploy response', file=sys.stderr)
    sys.exit(1)
print(uuid)
" "${DEPLOY_JSON}"
) || _die "Could not extract deploy UUID."

DOWNLOAD_URL="${CPK_API}/api/server/client-deploys/${DEPLOY_UUID}/download/"

EXPECTED_CHECKSUM=$(
    python3 -c "
import sys, json
data = json.loads(sys.argv[1])
print(data.get('checksum') or '')
" "${DEPLOY_JSON}"
)

_info "Latest version: ${DEPLOY_VERSION}  (uuid: ${DEPLOY_UUID})"

# ---------------------------------------------------------------------------
# Download the release archive
# ---------------------------------------------------------------------------

WORK_DIR=$(mktemp -d)
trap 'rm -rf "${WORK_DIR}"' EXIT

ARCHIVE_PATH="${WORK_DIR}/release.tar.gz"

_info "Downloading release archive…"

curl -L -f \
    -H "Authorization: ${TOKEN}" \
    -o "${ARCHIVE_PATH}" \
    "${DOWNLOAD_URL}" \
    || _die "Failed to download release archive from: ${DOWNLOAD_URL}"

# ---------------------------------------------------------------------------
# Verify checksum (SHA-256) when provided
# ---------------------------------------------------------------------------

if [[ -n "${EXPECTED_CHECKSUM}" ]]; then
    _info "Verifying SHA-256 checksum…"
    ACTUAL_CHECKSUM=$(python3 -c "
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], 'rb') as f:
    for chunk in iter(lambda: f.read(65536), b''):
        h.update(chunk)
print(h.hexdigest())
" "${ARCHIVE_PATH}")

    if [[ "${ACTUAL_CHECKSUM}" != "${EXPECTED_CHECKSUM}" ]]; then
        _die "Checksum mismatch! expected=${EXPECTED_CHECKSUM} actual=${ACTUAL_CHECKSUM}"
    fi
    _info "Checksum OK."
else
    _warn "No checksum provided by server — skipping verification."
fi

# ---------------------------------------------------------------------------
# Extract the archive
# ---------------------------------------------------------------------------

INSTALL_DIR="${PWD}/controlpanel-kitchen-linux-client"

if [[ -d "${INSTALL_DIR}" ]]; then
    _info "Removing existing installation directory…"
    rm -rf "${INSTALL_DIR}"
fi
mkdir -p "${INSTALL_DIR}"

_info "Extracting archive to ${INSTALL_DIR}…"
tar -xzf "${ARCHIVE_PATH}" --strip-components=1 -C "${INSTALL_DIR}"

# ---------------------------------------------------------------------------
# Run install.sh
# ---------------------------------------------------------------------------

_info "Running 'install.sh' in ${INSTALL_DIR}…"
(cd "${INSTALL_DIR}" && bash install.sh)

_info "Installation complete."
printf '\nYou can now start the CPK agent. Token is stored at %s\n' "${CPK_CREDENTIALS_FILE}"
