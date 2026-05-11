#!/usr/bin/env bash
# Install GitHub Actions self-hosted runner for canarylegal/canarycms (Linux x64).
# Registration tokens expire quickly and must not be committed — get a new one from:
#   Repo → Settings → Actions → Runners → New self-hosted runner
#
# Usage:
#   ./scripts/setup-self-hosted-runner.sh              # download + extract only
#   RUNNER_REGISTRATION_TOKEN='*****' ./scripts/setup-self-hosted-runner.sh --configure
#
# After configure, run interactively:  cd "$RUNNER_DIR" && ./run.sh
# Or install as a service (recommended): cd "$RUNNER_DIR" && sudo ./svc.sh install && sudo ./svc.sh start
#
# Public repo warning: forks can open PRs that target self-hosted runners — see GitHub docs.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/canarylegal/canarycms}"
RUNNER_VERSION="${RUNNER_VERSION:-2.334.0}"
RUNNER_DIR="${RUNNER_DIR:-${HOME}/actions-runner-canarycms}"
ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
DOWNLOAD_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ARCHIVE}"

# Official checksum from GitHub's "Optional: Validate the hash" for this release (update when bumping RUNNER_VERSION).
case "${RUNNER_VERSION}" in
  2.334.0)
    EXPECTED_SHA256="048024cd2c848eb6f14d5646d56c13a4def2ae7ee3ad12122bee960c56f3d271"
    ;;
  *)
    EXPECTED_SHA256=""
    ;;
esac

do_configure=false
for arg in "${@:-}"; do
  if [[ "$arg" == "--configure" ]]; then
    do_configure=true
  fi
done

mkdir -p "${RUNNER_DIR}"
cd "${RUNNER_DIR}"

if [[ ! -f config.sh ]]; then
  echo "Downloading Actions runner v${RUNNER_VERSION}..."
  curl -fsSL -o "${ARCHIVE}" -L "${DOWNLOAD_URL}"
  if [[ -n "${EXPECTED_SHA256}" ]]; then
    echo "${EXPECTED_SHA256}  ${ARCHIVE}" | shasum -a 256 -c
  else
    echo "WARN: No pinned SHA256 for v${RUNNER_VERSION}; skipping checksum (set EXPECTED_SHA256 in script or verify manually)." >&2
  fi
  tar xzf "./${ARCHIVE}"
  rm -f "./${ARCHIVE}"
  sudo ./bin/installdependencies.sh 2>/dev/null || true
fi

if [[ "${do_configure}" == true ]]; then
  token="${RUNNER_REGISTRATION_TOKEN:-}"
  if [[ -z "${token}" ]]; then
    echo "ERROR: Set RUNNER_REGISTRATION_TOKEN to the token from GitHub (New self-hosted runner)." >&2
    exit 1
  fi
  ./config.sh --url "${REPO_URL}" --token "${token}" --unattended --replace \
    --name "${RUNNER_NAME:-$(hostname -s)-canary-deploy}" --work _work
  echo "Configured. Start with: cd ${RUNNER_DIR} && ./run.sh"
  echo "Or install service: cd ${RUNNER_DIR} && sudo ./svc.sh install && sudo ./svc.sh start"
else
  echo "Runner files ready in: ${RUNNER_DIR}"
  echo "Configure (use a fresh token from GitHub):"
  echo "  RUNNER_REGISTRATION_TOKEN='…' ${0} --configure"
fi
