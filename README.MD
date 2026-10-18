# PiRowFlo for WaterRower

PiRowFlo connects a WaterRower or SmartRow to Bluetooth FTMS and ANT+ devices,
allowing rowing data to be used by compatible apps and sports watches.

This repository is a fork of the original
[PiRowFlo project by inonoob](https://github.com/inonoob/pirowflo).

> This fork contains substantial changes compared with the original PiRowFlo
> project. The original project, documentation and authors remain credited
> below.

<p align="center">
  <img src="docs/logo/PIROWFLO2.png" width="320" alt="PiRowFlo">
</p>

## About this fork

This fork extends and modernizes PiRowFlo, with a particular focus on reliable
SmartRow operation.

Major changes include:

- improved SmartRow Bluetooth connection and recovery
- automatic recovery when SmartRow goes to sleep or wakes up
- separate configurable Bluetooth adapters for SmartRow input and FTMS output
- improved FTMS data handling
- simultaneous Bluetooth FTMS and ANT+ operation
- improved ANT+ handling
- Supervisor and systemd integration
- integration with the PiRowFlo Control API
- Flutter-based PiRowFlo Control App
- automated installation and update tooling
- support for current Raspberry Pi OS and Python 3.13
- optional OLED/screen dependencies instead of installing them by default

## Architecture

For a SmartRow setup, PiRowFlo uses one Bluetooth controller to communicate
with SmartRow and another controller to provide the Bluetooth FTMS service.

```text
                         SmartRow
                            |
                     Bluetooth LE
                            |
                            v
                  Bluetooth Adapter 1
                            |
                            v
                       PiRowFlo
                      /        \
                     /          \
                    v            v
             Bluetooth FTMS     ANT+
                    |            |
                    v            v
             Bluetooth        ANT+ USB
              Adapter 2        Dongle
                    |            |
                    +------v-----+
                           |
                     Apps / Watches
```

PiRowFlo can operate with Bluetooth FTMS, ANT+, or both simultaneously.

## Features

- SmartRow as rowing data source via Bluetooth LE
- WaterRower S4 Monitor support
- Bluetooth FTMS broadcasting
- ANT+ broadcasting
- simultaneous Bluetooth FTMS and ANT+ operation
- SmartRow sleep/wakeup handling
- automatic SmartRow reconnection
- Bluetooth recovery after connection failures
- configurable Bluetooth adapters
- Supervisor-based process management
- local control socket
- optional Control API
- optional Flutter Control App

## Hardware

### SmartRow setup

A SmartRow setup requires:

- Raspberry Pi or compatible Linux system
- SmartRow
- two Bluetooth controllers
- ANT+ USB dongle if ANT+ output is required
- network connection for the optional Control API

Two Bluetooth controllers are required when SmartRow input and Bluetooth FTMS
output are used simultaneously.

A typical Raspberry Pi configuration is:

```text
Bluetooth Adapter 1
    SmartRow input

Bluetooth Adapter 2
    FTMS advertising

ANT+ USB Dongle
    ANT+ broadcasting
```

On a Raspberry Pi with integrated Bluetooth, the integrated controller can be
used as one of the two adapters.

For example:

```text
Integrated Bluetooth -> FTMS
USB Bluetooth dongle -> SmartRow
ANT+ USB dongle      -> ANT+
```

The exact adapter assignment is configurable and is not tied to `hci0` or
`hci1`.

## Installation

For new installations, use the dedicated PiRowFlo Installer:

https://github.com/stampede79/pirowflo-installer

On a fresh Raspberry Pi OS Lite installation:

```bash
sudo apt update
sudo apt install -y git

git clone https://github.com/stampede79/pirowflo-installer.git
cd pirowflo-installer

sudo ./install.sh
```

The installer sets up:

- PiRowFlo
- Python virtual environment
- required system dependencies
- Supervisor
- systemd services
- Bluetooth support
- ANT+ USB permissions
- PiRowFlo Control API
- API key
- optional Bluetooth adapter configuration

The default installation paths are:

```text
/opt/pirowflo
/opt/pirowflo-control-api
```

## Bluetooth configuration

Bluetooth adapter configuration is stored in:

```text
/etc/pirowflo.env
```

Example:

```text
PIROWFLO_SMARTROW_ADAPTER_MAC=00:1A:7D:DA:71:15
PIROWFLO_FTMS_ADAPTER_MAC=B8:27:EB:1D:E3:3E
```

Do not copy these example MAC addresses to another system. Each Bluetooth
controller has its own address.

The installer provides an interactive configuration utility:

```bash
cd ~/pirowflo-installer
sudo ./configure-bluetooth.sh
```

The utility lists the available Bluetooth controllers and asks which controller
should be used for:

- SmartRow
- FTMS

The Bluetooth adapters do not have to be connected during the initial
installation. Configuration can be performed later.

## Operating modes

PiRowFlo provides several Supervisor profiles.

### SmartRow - Bluetooth + ANT+

This is the normal combined SmartRow mode:

```text
pirowflo_SR_SmartRow_Bluetooth_AntPlus
```

It reads rowing data from SmartRow and broadcasts it using both Bluetooth FTMS
and ANT+.

### SmartRow - Bluetooth only

```text
pirowflo_SR_Smartrow_Bluetooth_only
```

Reads SmartRow data and broadcasts Bluetooth FTMS only.

### SmartRow - ANT+ only

```text
pirowflo_SR_Smartrow_AntPlus_only
```

Reads SmartRow data and broadcasts ANT+ only.

S4 Monitor profiles are also available.

## Service management

PiRowFlo is managed by Supervisor running as a systemd service.

Check Supervisor:

```bash
systemctl status supervisord.service
```

Check the individual PiRowFlo processes:

```bash
/opt/pirowflo/venv/bin/supervisorctl \
  -c /opt/pirowflo/services/supervisord.conf \
  status
```

A typical SmartRow combined setup should show:

```text
pirowflo_SR_SmartRow_Bluetooth_AntPlus   RUNNING
```

## Logs

The PiRowFlo log is located at:

```text
/opt/pirowflo/src/pirowflo.log
```

Follow the log:

```bash
tail -f /opt/pirowflo/src/pirowflo.log
```

Show the latest entries:

```bash
tail -n 100 /opt/pirowflo/src/pirowflo.log
```

Supervisor logs can also be inspected with:

```bash
journalctl -u supervisord.service
```

## Updating

When PiRowFlo was installed using the PiRowFlo Installer, both PiRowFlo and the
Control API can be updated with:

```bash
cd ~/pirowflo-installer
sudo ./update.sh
```

The updater:

1. checks both Git repositories for local modifications
2. stops PiRowFlo and the Control API
3. updates the repositories using fast-forward-only Git pulls
4. updates Python dependencies
5. regenerates local PiRowFlo configuration
6. restarts the services

Local modifications cause the update to abort rather than overwrite them.

## Control API

PiRowFlo can optionally be controlled through the separate PiRowFlo Control API:

https://github.com/stampede79/pirowflo-control-api

The API provides functionality for:

- reading PiRowFlo status
- reading SmartRow connection status
- starting PiRowFlo profiles
- stopping PiRowFlo
- restarting PiRowFlo
- resetting the current SmartRow/PiRowFlo session

The default API port is:

```text
8090
```

API configuration is stored in:

```text
/etc/pirowflo-control.env
```

The API is protected by an API key.

## PiRowFlo Control App

A Flutter-based Android control application is available separately:

https://github.com/stampede79/pirowflo-control-app

The app communicates with the PiRowFlo Control API and provides a mobile
interface for:

- PiRowFlo status
- SmartRow status
- Bluetooth + ANT+ mode
- Bluetooth-only mode
- ANT+-only mode
- restart
- stop
- reset

The server URL configured in the app should include the protocol and API port.

Example:

```text
http://192.168.1.100:8090
```

## Optional OLED / Screen support

The original PiRowFlo project contains support for an OLED display and
Raspberry Pi GPIO controls.

These components are optional in this fork and are not installed as part of the
normal PiRowFlo core dependencies.

Core dependencies are installed from:

```text
requirements.txt
```

For the optional screen components:

```bash
/opt/pirowflo/venv/bin/pip install \
  -r /opt/pirowflo/requirements-screen.txt
```

The optional screen requirements include:

- `luma.oled`
- `pigpio`
- `spidev`

Existing screen-related source code and hardware documentation are retained in
the repository.

## Troubleshooting

### SmartRow is not found

Check the configured Bluetooth adapters:

```bash
cat /etc/pirowflo.env
```

List available Bluetooth controllers:

```bash
bluetoothctl list
```

Check whether Bluetooth is blocked:

```bash
rfkill list bluetooth
```

If necessary:

```bash
sudo rfkill unblock bluetooth
```

Then check the PiRowFlo log:

```bash
tail -n 100 /opt/pirowflo/src/pirowflo.log
```

### ANT+ dongle is not ready

Check whether the ANT+ USB dongle is detected:

```bash
lsusb
```

A Dynastream ANTUSB2 stick typically appears with USB ID:

```text
0fcf:1008
```

The installer creates a udev rule that grants the `plugdev` group access to the
ANT+ USB device.

Check the device permissions if ANT+ cannot start.

### Bluetooth FTMS does not start

Check the Bluetooth controllers:

```bash
bluetoothctl list
```

Then inspect the PiRowFlo log:

```bash
grep -iE 'BLE|FTMS|BlueZ' /opt/pirowflo/src/pirowflo.log | tail -100
```

### PiRowFlo repeatedly restarts

Check Supervisor:

```bash
/opt/pirowflo/venv/bin/supervisorctl \
  -c /opt/pirowflo/services/supervisord.conf \
  status
```

Check stderr:

```bash
/opt/pirowflo/venv/bin/supervisorctl \
  -c /opt/pirowflo/services/supervisord.conf \
  tail pirowflo_SR_SmartRow_Bluetooth_AntPlus stderr
```

And inspect the main log:

```bash
tail -n 100 /opt/pirowflo/src/pirowflo.log
```

## Historical upstream documentation

This repository is based on the original PiRowFlo project.

The upstream project originally focused on connecting WaterRower hardware to a
Raspberry Pi and broadcasting rowing data over Bluetooth and ANT+ so that the
same rowing data could be consumed by training apps and Garmin devices.

The original project also introduced SmartRow support and optional OLED/GPIO
hardware.

Some documentation and images from the original project are retained under:

```text
docs/
```

Older application compatibility information and hardware documentation may
refer to the state of the upstream project around 2021 and should not
necessarily be considered current compatibility information for this fork.

## Credits

This project is based on the original
[PiRowFlo project by inonoob](https://github.com/inonoob/pirowflo).

Large parts of the original architecture, protocol implementation,
documentation and hardware support originate from the upstream project.

This fork builds on that work and adds the SmartRow reliability, recovery,
configuration, installation and control functionality described above.

Additional upstream projects used by the original PiRowFlo implementation are
documented in the repository history and source files.

## License

PiRowFlo is licensed under the GNU General Public License v3.0.

See [LICENSE](LICENSE) for the complete license text.
