#!/usr/bin/env bash
# Install reproducible ffmpeg and ffprobe without depending on Ubuntu apt DNS.
# Both binaries come from the same immutable, multi-arch upstream image.
set -euo pipefail

if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  ffmpeg -version | sed -n '1p'
  ffprobe -version | sed -n '1p'
  exit 0
fi

: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_PATH:?GITHUB_PATH is required}"

# Verified published digest for the upstream 9.0.2-1 multi-arch image.
image='mwader/static-ffmpeg@sha256:f5d100184884eb3e82b0eb14bb5ebf98da99826ac824989720297fb9ef21c822'
tool_dir="${RUNNER_TEMP}/ksu-media-tools/bin"
mkdir -p "${tool_dir}"

docker pull --quiet "${image}"
cid="$(docker create "${image}")"
trap 'docker rm -f "${cid}" >/dev/null 2>&1 || true' EXIT

docker cp "${cid}:/ffmpeg" "${tool_dir}/ffmpeg"
docker cp "${cid}:/ffprobe" "${tool_dir}/ffprobe"
chmod 0755 "${tool_dir}/ffmpeg" "${tool_dir}/ffprobe"
test -x "${tool_dir}/ffmpeg"
test -x "${tool_dir}/ffprobe"

printf '%s\n' "${tool_dir}" >> "${GITHUB_PATH}"
export PATH="${tool_dir}:${PATH}"
ffmpeg -version | sed -n '1p'
ffprobe -version | sed -n '1p'
