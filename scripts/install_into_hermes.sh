#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/hermes-home-or-repo" >&2
  exit 1
fi

TARGET=$1
case "$TARGET" in
  ~*) TARGET="$HOME${TARGET#~}" ;;
esac

if [ -d "$TARGET/plugins" ]; then
  HERMES_HOME="$TARGET"
elif [ -d "$TARGET/.hermes/plugins" ]; then
  HERMES_HOME="$TARGET/.hermes"
else
  echo "Could not find a Hermes plugins directory under: $TARGET" >&2
  echo "Expected either <path>/plugins or <path>/.hermes/plugins" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../plugin/klokkan"
DEST_DIR="$HERMES_HOME/plugins/klokkan"

mkdir -p "$(dirname "$DEST_DIR")"
rm -rf "$DEST_DIR"
cp -R "$SRC_DIR" "$DEST_DIR"

echo "Installed Klokkan plugin to: $DEST_DIR"
