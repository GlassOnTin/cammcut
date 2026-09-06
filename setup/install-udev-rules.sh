#!/bin/sh
# Install udev rules granting the plugdev group access to the PL2305
# USB-parallel adapter. Run with sudo. After this, cammcut talks to
# /dev/usb/lpN without root.
set -e

RULES=/etc/udev/rules.d/99-roland-cutter.rules

cat > "$RULES" <<'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="067b", ATTRS{idProduct}=="2305", MODE="0660", GROUP="plugdev"
SUBSYSTEM=="usbmisc", ATTRS{idVendor}=="067b", ATTRS{idProduct}=="2305", MODE="0660", GROUP="plugdev"
EOF

udevadm control --reload

# Retrigger existing nodes so no replug is needed. The usblp character
# nodes live under /sys/class/usbmisc (the raw usb rule alone does not
# touch them — learned the hard way).
for d in /sys/class/usbmisc/lp*; do
    [ -e "$d" ] && udevadm trigger --action=change "$d" || true
done

echo "installed $RULES"
echo "nodes now:"
ls -l /dev/usb/lp* 2>/dev/null || echo "  (no usblp nodes present)"