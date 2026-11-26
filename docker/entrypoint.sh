#!/bin/sh
set -eu

config_dir="${HOME}/.config/trove"
mkdir -p "$config_dir"

if [ -n "${TROVE_PASSWORD:-}" ]; then
    temporary="${config_dir}/.password.$$"
    printf '%s\n' "$TROVE_PASSWORD" >"$temporary"
    chmod 0600 "$temporary"
    mv "$temporary" "${config_dir}/password"
fi

if [ ! -f "${config_dir}/llm.toml" ]; then
    temporary="${config_dir}/.llm.$$"
    printf 'enabled = false\n' >"$temporary"
    chmod 0600 "$temporary"
    mv "$temporary" "${config_dir}/llm.toml"
fi

if [ "$#" -eq 0 ]; then
    set -- serve
fi

case "$1" in
    init|serve|worker)
        if [ ! -f "${config_dir}/password" ]; then
            echo "Missing ${config_dir}/password; start once with TROVE_PASSWORD set or create the file." >&2
            exit 1
        fi
        export TROVE_PASSWORD_FILE="${config_dir}/password"
        ;;
esac

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
