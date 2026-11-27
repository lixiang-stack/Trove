#!/bin/sh
set -eu

home="${HOME}/Trove"
mkdir -p "$home"

# Create the full template on a fresh volume. On an upgraded volume, keep the
# existing settings but add [server] with a container-reachable host if the
# legacy config predates that section. An explicit [server] section is
# preserved.
trove config init --host 0.0.0.0

if [ "$#" -eq 0 ]; then
    set -- serve
fi

if [ "${1:-}" = "init" ]; then
    trove db upgrade
    if python -c "import funasr" >/dev/null 2>&1; then
        trove setup
    else
        echo "Skipping ASR model download: base image. Rebuild with INSTALL_ASR=true for transcription." >&2
    fi
    exit 0
fi

exec trove "$@"
