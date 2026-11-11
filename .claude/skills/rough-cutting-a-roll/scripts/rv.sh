#!/usr/bin/env bash
# Run a Python script against the running DaVinci Resolve Studio (scripting API).
# Resolve must be running with a project open, and Preferences > System > General >
# "External scripting using" set to Local. Paths can be overridden with the env vars below.
case "$(uname -s)" in
  Darwin)
    : "${RESOLVE_SCRIPT_API:=/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting}"
    : "${RESOLVE_SCRIPT_LIB:=/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so}" ;;
  *)
    : "${RESOLVE_SCRIPT_API:=/opt/resolve/Developer/Scripting}"
    : "${RESOLVE_SCRIPT_LIB:=/opt/resolve/libs/Fusion/fusionscript.so}" ;;
esac
export RESOLVE_SCRIPT_API RESOLVE_SCRIPT_LIB
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$RESOLVE_SCRIPT_API/Modules/"
export PYTHONIOENCODING=utf-8          # Turkish text; the system locale may be ASCII
exec "${RESOLVE_PYTHON:-python3}" "$@"
