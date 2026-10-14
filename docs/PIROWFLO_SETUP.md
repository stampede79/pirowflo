# PiRowFlo – SmartRow Setup

Diese Installation verwendet PiRowFlo als Bridge zwischen einem WaterRower mit
SmartRow und zwei parallelen Ausgabekanälen:

```text
                       BLE / FTMS
                  ┌────────────────► WATERROWER Connect
                  │
SmartRow ──BLE──► PiRowFlo
                  │
                  └────────────────► Garmin
                       ANT+ FE
```

## Hardware

- Raspberry Pi
- integrierter Bluetooth-Adapter
  - MAC: `B8:27:EB:1D:E3:3E`
  - Verbindung zum SmartRow
- USB-Bluetooth-Dongle (Cambridge Silicon Radio)
  - MAC: `00:1A:7D:DA:71:15`
  - stellt BLE/FTMS für WATERROWER Connect bereit
- Dynastream ANTUSB2
  - USB-ID: `0fcf:1008`
  - ANT+ Fitness Equipment für Garmin
- SmartRow
  - MAC: `E8:F6:A2:1E:C4:69`

Die Linux-Namen `hci0` und `hci1` sind nicht stabil und können sich nach einem
Neustart ändern. PiRowFlo wählt die Bluetooth-Adapter deshalb anhand ihrer
physischen MAC-Adressen aus.

## ANTUSB2

Der ANTUSB2 wird von neueren Linux-Versionen möglicherweise automatisch durch
`usb_serial_simple` als Suunto Serial Converter gebunden.

Das verhindert den direkten Zugriff von PiRowFlo auf den ANTUSB2.

### Kernel-Treiber deaktivieren

Datei:

```text
/etc/modprobe.d/blacklist-antusb.conf
```

Inhalt:

```text
# PiRowFlo accesses the Dynastream ANTUSB2 directly via libusb.
# Prevent Linux from binding it as a Suunto serial converter.
blacklist usb_serial_simple
```

Nach einem Neustart prüfen:

```bash
lsusb
lsusb -t
```

Der ANTUSB2 sollte erscheinen als:

```text
0fcf:1008 Dynastream Innovations, Inc. ANTUSB2 Stick
```

Während PiRowFlo ihn verwendet, kann bei `lsusb -t` beispielsweise `usbfs`
angezeigt werden. Er darf nicht an `usb_serial_simple` gebunden sein.

## USB-Berechtigungen für ANTUSB2

PiRowFlo läuft als Benutzer `pi` und benötigt direkten Zugriff auf den ANTUSB2.

Datei:

```text
/etc/udev/rules.d/99-antusb.rules
```

Inhalt:

```text
SUBSYSTEM=="usb", ATTR{idVendor}=="0fcf", ATTR{idProduct}=="1008", MODE="0660", GROUP="plugdev"
```

Der Benutzer `pi` muss Mitglied von `plugdev` sein:

```bash
groups pi
```

Falls notwendig:

```bash
sudo usermod -aG plugdev pi
```

udev-Regeln neu laden:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Supervisor

Für den normalen Betrieb wird ausschließlich das kombinierte SmartRow-Profil
verwendet:

```text
pirowflo_SR_SmartRow_Bluetooth_AntPlus
```

Lokale Datei:

```text
~/pirowflo/services/supervisord.conf
```

Relevante Konfiguration:

```ini
[program:pirowflo_SR_SmartRow_Bluetooth_AntPlus]
user=pi
command=/home/pi/pirowflo/venv/bin/python3 /home/pi/pirowflo/src/waterrowerthreads.py -i sr -b -a
autostart=true
autorestart=true
startretries=10
```

`services/supervisord.conf` ist in `.gitignore` enthalten und wird daher nicht
mit dem Repository versioniert.

Supervisor-Konfiguration nach Änderungen laden:

```bash
~/pirowflo/venv/bin/supervisorctl \
  -c ~/pirowflo/services/supervisord.conf reread

~/pirowflo/venv/bin/supervisorctl \
  -c ~/pirowflo/services/supervisord.conf update
```

Status prüfen:

```bash
~/pirowflo/venv/bin/supervisorctl \
  -c ~/pirowflo/services/supervisord.conf status
```

Im normalen Betrieb sollte nur dieses PiRowFlo-Profil laufen:

```text
pirowflo_SR_SmartRow_Bluetooth_AntPlus   RUNNING
```

## SmartRow / BlueZ Recovery

BlueZ kann insbesondere nach einem Neustart ein zuvor entdecktes SmartRow
Device-Objekt verlieren.

Ein normaler temporärer Verbindungsfehler wie:

```text
le-connection-abort-by-local
```

wird von PiRowFlo erneut versucht.

Bei:

```text
Device does not exist
```

beendet PiRowFlo dagegen den Prozess. Supervisor startet ihn anschließend neu,
sodass eine vollständige SmartRow-Discovery durchgeführt wird.

## BLE / WATERROWER Connect

PiRowFlo stellt über den USB-Bluetooth-Dongle einen FTMS-Service bereit.

Wichtig für WATERROWER Connect:

- Rower Data: `0x2AD1`
- PiRowFlo sendet Rower Data kontinuierlich mit 1 Hz
- Notifications werden auch gesendet, wenn sich während einer Pause keine
  Ruderwerte ändern

Das kontinuierliche Senden ist notwendig, damit WATERROWER Connect auch nach
längeren Ruderpausen zuverlässig weiterarbeitet.

## ANT+ / Garmin

PiRowFlo verwendet den ANTUSB2 als ANT+ Fitness Equipment Sender.

Die Garmin-Uhr erkennt PiRowFlo als:

```text
Trainer
```

Übertragen werden unter anderem die ANT+ Fitness Equipment / Rowing-Daten.

BLE und ANT+ können gleichzeitig verwendet werden:

```text
WATERROWER Connect  ← BLE/FTMS ← PiRowFlo → ANT+ FE → Garmin
```

## Funktionstest nach einem Neustart

Nach dem Boot muss kein PiRowFlo-Prozess manuell gestartet werden.

1. SmartRow durch Ziehen am Griff aufwecken.
2. Supervisor prüfen:

```bash
~/pirowflo/venv/bin/supervisorctl \
  -c ~/pirowflo/services/supervisord.conf status
```

3. ANTUSB2 prüfen:

```bash
lsusb -t
```

4. WATERROWER Connect mit PiRowFlo verbinden.
5. Garmin mit dem ANT+ Trainer verbinden.
6. Rudern.
7. Eine längere Pause machen.
8. Weiterrudern.

Beide Geräte sollten nach der Pause weiterhin Daten erhalten.

## Relevante Git-Commits

```text
862caf0  Fix SmartRow BLE adapter handling and FTMS data streaming
e84e463  Improve SmartRow BlueZ connection recovery
```

## GitHub-Zugriff

Das Repository verwendet auf diesem Raspberry SSH für GitHub.

Remote prüfen:

```bash
git remote -v
```

Der Remote sollte auf die SSH-URL zeigen:

```text
git@github.com:stampede79/pirowflo.git
```
