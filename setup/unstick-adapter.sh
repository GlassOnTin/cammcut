#!/bin/sh
# Recover a stalled PL2305 USB-parallel adapter.
#
# Symptom: every write to /dev/usb/lpN "succeeds" but the machine ignores
# everything and shows no error. Cause: something read from the device,
# the adapter's bulk endpoints halted (-EPIPE, visible in dmesg as
# "nonzero read bulk status received: -32"), and the kernel's usblp
# driver does not clear the halt on its own.
#
# Fix: cycle the usblp driver on the interface, which clears the stall.
# Run with sudo. Takes effect immediately; no replug needed.
set -e

DRIVER=/sys/bus/usb/drivers/usblp

found=0
for iface in "$DRIVER"/[0-9]*:*.*; do
    [ -e "$iface" ] || continue
    name=${iface##*/}

    # Only touch Prolific PL2305 interfaces; leave printers alone.
    dev=$(dirname "$(readlink -f "$iface")")
    vid=$(cat "$dev/idVendor" 2>/dev/null || true)
    pid=$(cat "$dev/idProduct" 2>/dev/null || true)
    if [ "$vid" != "067b" ] || [ "$pid" != "2305" ]; then
        echo "skipping $name (vid:pid $vid:$pid)"
        continue
    fi
    found=1

    echo "$name" > "$DRIVER/unbind"
    sleep 1
    echo "$name" > "$DRIVER/bind"
    echo "cycled $name — endpoint stall cleared"
done

[ "$found" = 1 ] || echo "no bound PL2305 usblp interface found (is the adapter plugged in?)"