#!/bin/sh
set -e

LOGFILE="/tmp/events.log"
rm -f "$LOGFILE"
touch "$LOGFILE"

# Trap SIGTERM and SIGINT to gracefully terminate children and clean up
cleanup() {
    echo "Caught stop signal, terminating processes..."
    kill -TERM "$PIPE_PID" 2>/dev/null || true
    kill -TERM "$DSD_PID" 2>/dev/null || true
    wait "$PIPE_PID" 2>/dev/null || true
    wait "$DSD_PID" 2>/dev/null || true
    rm -f "$LOGFILE"
    exit 0
}
trap cleanup TERM INT

# 1. Stream the log file continuously into Python using tail -F (never exits on EOF)
tail -n +1 -F "$LOGFILE" | python3 -u /app/parser.py &
PIPE_PID=$!

FREQ="${FREQ:-856.5865M}"

CHAN_MAP_ARGS=""
if [ -n "$CHAN_MAP" ]; then
    # Adjust flag syntax to your input tool/tuner (e.g. -f 851.375M or rtl_fm / rtl_sdr flags)
    CHAN_MAP_ARGS="-C $CHAN_MAP"
fi

# 2. Run dsd-fme in the background writing directly to the log file
# Discard console visual logs to /dev/null if desired
dsd-fme -ft -ma -T $CHAN_MAP_ARGS -i rtl:0:$FREQ:0:0 -o null -J "$LOGFILE" > /dev/null &
DSD_PID=$!

# Wait for dsd-fme; when SIGTERM arrives, wait is interrupted and triggers cleanup
wait "$DSD_PID"
cleanup
