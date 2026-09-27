#!/bin/sh
set -e

# Create a temporary named pipe
PIPE="/tmp/dsd_json.fifo"
rm -f "$PIPE"
mkfifo "$PIPE"

# 1. Start the Python ingestion consumer in the background reading from the FIFO
python3 -u /app/ingest.py < "$PIPE" &
PYTHON_PID=$!

FREQ="${FREQ:-856.5865M}"

CHAN_MAP_ARGS=""
if [ -n "$CHAN_MAP" ]; then
    # Adjust flag syntax to your input tool/tuner (e.g. -f 851.375M or rtl_fm / rtl_sdr flags)
    CHAN_MAP_ARGS="-C $CHAN_MAP"
fi

# 2. Run dsd-fme writing its JSON directly to the FIFO
# Discard console visual logs to /dev/null if desired
dsd-fme -ft -ma -T $CHAN_MAP_ARGS -i rtl:0:$FREQ:0:0 -o null -J "$PIPE" > /dev/null

# Clean up
wait $PYTHON_PID
rm -f "$PIPE"
