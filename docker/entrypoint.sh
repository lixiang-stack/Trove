#!/bin/sh
set -eu

if [ "${1:-}" = "init" ]; then
    trove db upgrade
    if python -c "import funasr" >/dev/null 2>&1; then
        trove setup
    else
        echo "Skipping ASR model download: base image. Rebuild with INSTALL_ASR=true for transcription." >&2
    fi
    exit 0
fi

if [ "$#" -eq 0 ]; then
    set -- serve
fi
exec trove "$@"
