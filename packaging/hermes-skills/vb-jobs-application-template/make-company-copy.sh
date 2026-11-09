#!/bin/zsh
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "Usage: ./make-company-copy.sh Company-Name" >&2
  exit 64
fi
COMPANY="$1"
BASE_DIR="${VB_JOBS_APPLICATIONS_DIR:-$HOME/Hermes/job-applications}"
DEST="$BASE_DIR/$COMPANY"
mkdir -p "$DEST"
for f in headshot.png build_resume.js build_letter.js package.json README.md manifest.json; do
  cp -f "$f" "$DEST/$f"
done
if [[ -d node_modules ]]; then
  cp -R node_modules "$DEST/node_modules"
fi
echo "$DEST"
