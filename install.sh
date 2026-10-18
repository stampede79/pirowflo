#!/usr/bin/env bash

cat <<'EOF'

PiRowFlo installation has moved to the dedicated installer:

  https://github.com/stampede79/pirowflo-installer

For a new installation use:

  sudo apt update
  sudo apt install -y git

  git clone https://github.com/stampede79/pirowflo-installer.git
  cd pirowflo-installer
  sudo ./install.sh

See README.MD for additional information.

EOF

exit 0
