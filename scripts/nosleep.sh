#!/bin/bash
# Stops the Debian 4700S from ever sleeping and keeps it reachable over the network.
# Run as root: sudo bash nosleep.sh
set -euo pipefail

# 1. Block every kind of sleep at the systemd level (GNOME, logind, and anything else).
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

# 2. logind: ignore power/suspend keys and idle.
mkdir -p /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/90-nosleep.conf <<'EOF'
[Login]
HandleSuspendKey=ignore
HandleHibernateKey=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF

# 3. GNOME: no automatic suspend, including on the GDM login screen.
if [ -d /etc/dconf ]; then
  mkdir -p /etc/dconf/db/gdm.d /etc/dconf/db/local.d
  for f in /etc/dconf/db/gdm.d/90-nosleep /etc/dconf/db/local.d/90-nosleep; do
    cat > "$f" <<'EOF'
[org/gnome/settings-daemon/plugins/power]
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
power-button-action='nothing'
EOF
  done
  [ -f /etc/dconf/profile/user ] || printf 'user-db:user\nsystem-db:local\n' > /etc/dconf/profile/user
  grep -q '^system-db:local' /etc/dconf/profile/user || echo 'system-db:local' >> /etc/dconf/profile/user
  # Lock the keys: otherwise a user value (set from GNOME Settings) wins over the system one.
  mkdir -p /etc/dconf/db/local.d/locks
  printf '%s\n' /org/gnome/settings-daemon/plugins/power/sleep-inactive-ac-type \
                /org/gnome/settings-daemon/plugins/power/sleep-inactive-battery-type \
    > /etc/dconf/db/local.d/locks/90-nosleep
  dconf update
fi

# 4. Keep Wake-on-LAN enabled on the wired link (safety net).
if command -v nmcli >/dev/null; then
  nmcli -t -f NAME,TYPE con show | awk -F: '$2=="802-3-ethernet"{print $1}' | while read -r c; do
    nmcli con modify "$c" 802-3-ethernet.wake-on-lan magic || true
  done
fi

# logind is not restarted (that can kill the GNOME session): the drop-in applies at the
# next reboot, and the mask in step 1 already blocks all sleep right away.
echo "--- check ---"
systemctl is-enabled sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target 2>&1 || true
