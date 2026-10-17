import gatt
import logging
import os
import dbus
import threading
from time import time, sleep

logger = logging.getLogger(__name__)

SMARTROW_ADAPTER_MAC = "00:1A:7D:DA:71:15"

def get_adapter_name_by_mac(mac_address):
    bus = dbus.SystemBus()

    manager = dbus.Interface(
        bus.get_object("org.bluez", "/"),
        "org.freedesktop.DBus.ObjectManager"
    )

    objects = manager.GetManagedObjects()

    for path, interfaces in objects.items():
        adapter = interfaces.get("org.bluez.Adapter1")

        if not adapter:
            continue

        address = str(adapter.get("Address", ""))

        if address.lower() == mac_address.lower():
            return path.rsplit("/", 1)[-1]

    raise RuntimeError(
        "Bluetooth adapter with MAC {} not found".format(mac_address)
    )

#This SDK requires you to create subclasses of gatt.DeviceManager and gatt.Device. The other two classes gatt.Service and gatt.Characteristic are not supposed to be subclassed.

#The SDK entry point is the DeviceManager class. Check the following example to dicover any Bluetooth Low Energy device nearby.


class SmartRow(gatt.Device):

    SERVICE_UUID_SMARTROW = "00001234-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_UUID_ROWWRITE = "00001235-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_UUID_ROWDATA = "00001236-0000-1000-8000-00805f9b34fb"

    def __init__(self, mac_address, manager):
        super().__init__(mac_address=mac_address, manager=manager)
        self._callbacks = set()
        self.lock = threading.Lock()
        self.is_connected = False
        self._rx_buffer = ""
        self.connect_failures = 0
        self.connection_failed_permanently = False
        self.waiting_for_wakeup = False

    def ready(self):
      with self.lock: #"Lock Acquired"
          return self.is_connected
      
    def connect_succeeded(self):
        super().connect_succeeded()
        logger.info("Connected to [{}]".format(self.mac_address))

    def connect_failed(self, error):
        super().connect_failed(error)

        error_text = str(error)

        if "Device does not exist" in error_text:
            logger.error(
                "SmartRow device object disappeared from BlueZ [%s] — "
                "requesting fresh discovery",
                self.mac_address
            )

            with self.lock:
                self.connection_failed_permanently = True

            try:
                self.manager.stop()
            except Exception:
                pass

            return

        self.connect_failures += 1

        logger.warning(
            "Connection failed [%s]: %s — attempt %d/3",
            self.mac_address,
            error,
            self.connect_failures
        )
        if self.connect_failures >= 3:
            logger.error(
                "SmartRow connection failed 3 times — removing stale BlueZ device "
                "and requesting fresh discovery"
            )

            with self.lock:
                self.connection_failed_permanently = True
            try:
                with open(_FORCE_SCAN_FILE, 'w') as f:
                    f.write(self.mac_address)
                logger.info("SmartRow force-scan marker created")
            except Exception as e:
                logger.warning("Could not create SmartRow force-scan marker: %s", e)

            try:
                self.manager.remove_device(self.mac_address)
                logger.info(
                    "Removed stale SmartRow device from BlueZ [%s]",
                    self.mac_address
                )
            except Exception as e:
                logger.warning(
                    "Could not remove stale SmartRow device from BlueZ [%s]: %s",
                    self.mac_address,
                    e
                )

            try:
                self.manager.stop()
            except Exception:
                pass

            return

        sleep(2)
        self.connect()

    def disconnect_succeeded(self):
        super().disconnect_succeeded()

        with self.lock:
            was_connected = self.is_connected
            self.is_connected = False
        if was_connected:
            logger.info(
                "SmartRow disconnected after successful connection [%s] — "
                "entering waiting-for-wakeup state",
                self.mac_address
            )

            with self.lock:
                self.waiting_for_wakeup = True

            try:
                self.manager.stop()
            except Exception:
                pass

            return

        logger.info(
            "SmartRow disconnected during connection setup [%s] — "
            "waiting for retry",
            self.mac_address
        )

    def find_service(self, uuid):
        for service in self.services:
            if service.uuid == uuid:
                return service

        return None

    def find_characteristic(self, service, uuid):
        for chrstc in service.characteristics:
            if chrstc.uuid == uuid:
                return chrstc

        return None

    def services_resolved(self):
        super().services_resolved()
        with self.lock:
            self.connect_failures = 0
            self.connection_failed_permanently = False
            self.waiting_for_wakeup = False

        logger.info("Resolved services [{}]".format(self.mac_address))
        for service in self.services:
            logger.info("\t[{}] Service [{}]".format(self.mac_address, service.uuid))
            for characteristic in service.characteristics:
                logger.info("\t\tCharacteristic [{}]".format(characteristic.uuid))

        self.serviceSmartRow = self.find_service(self.SERVICE_UUID_SMARTROW)
        self.chrstcRowData = self.find_characteristic(self.serviceSmartRow, self.CHARACTERISTIC_UUID_ROWDATA)
        self.chrstcRowData.enable_notifications()

        self.chrstcRowWrite = self.find_characteristic(self.serviceSmartRow, self.CHARACTERISTIC_UUID_ROWWRITE)
        with self.lock: #"Lock Acquired"
            self.is_connected = True
        
    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic, value)

        try:
            decoded = value.decode('latin-1')
        except Exception as e:
            logger.warning("decode error: %s raw: %s", e, value.hex())
            return

        # BLE notifications do not necessarily align with SmartRow message
        # boundaries. Keep incomplete data until a complete \r-terminated
        # SmartRow message has been received.
        self._rx_buffer += decoded

        while '\r' in self._rx_buffer:
            part, self._rx_buffer = self._rx_buffer.split('\r', 1)
            part = part.strip('\n')

            if part:
                self.notify_callbacks(part)

    def characteristic_write_value(self, value):
        self.writing = value
        #print(value)
        self.chrstcRowWrite.write_value(value)

    def register_callback(self, cb):
        self._callbacks.add(cb)

    def remove_callback(self, cb):
        self._callbacks.remove(cb)

    def notify_callbacks(self, event):
        for cb in self._callbacks:
            cb(event)

class SmartRowManager(gatt.DeviceManager):
    def __init__(self,*args,**kwargs):
        gatt.DeviceManager.__init__(self, *args, **kwargs)
        self.lock = threading.Lock()
        self.discovered=False

    def start_discovery(self):
        """Override gatt's default Transport:le filter with Transport:auto.

        gatt hardcodes SetDiscoveryFilter({'Transport': 'le'}) which is known
        to produce zero results on BCM43438 (Pi Zero W / Pi 3B, UART bus) with
        BlueZ 5.66 – the call succeeds but no InterfacesAdded signals arrive.
        bluetoothctl uses Transport:auto and reliably finds BLE devices on the
        same hardware, so we mirror that behaviour here.
        """
        try:
            self._adapter.SetDiscoveryFilter({'Transport': 'auto'})
            self._adapter.StartDiscovery()
        except Exception as e:
            dbus_name = getattr(e, 'get_dbus_name', lambda: '')()
            if dbus_name == 'org.bluez.Error.InProgress':
                pass
            else:
                raise

    def ready(self):
        with self.lock:
            return self.discovered
        
    def device_discovered(self, device):
        try:
            alias = device.alias()
        except Exception as e:
            logger.info("device_discovered: alias() failed for %s (%s) — retrying", device.mac_address, e)
            # Properties not yet loaded; try again via devices() scan
            try:
                for d in self.devices():
                    if d.mac_address == device.mac_address:
                        alias = d.alias()
                        break
                else:
                    return
            except Exception:
                return
        logger.info("discovered: alias=%s mac=%s", alias, device.mac_address)
        if alias == "SmartRow":
            logging.info("found SmartRow")
            logging.info(device.mac_address)
            self.smartrowmac = device.mac_address
            with self.lock:
                self.discovered = True
            try:
                self.stop()
            except Exception:
                pass  # stop() fails if run() hasn't been called yet (device in BlueZ cache)


_MAC_CACHE_FILE = '/tmp/pirowflo_smartrow_mac'
_FORCE_SCAN_FILE = '/tmp/pirowflo_smartrow_force_scan'


def _save_smartrow_mac(mac):
    try:
        with open(_MAC_CACHE_FILE, 'w') as f:
            f.write(mac)
        logger.info("SmartRow MAC cached to %s", _MAC_CACHE_FILE)
    except Exception as e:
        logger.warning("could not cache SmartRow MAC: %s", e)


def _load_smartrow_mac():
    try:
        if os.path.exists(_MAC_CACHE_FILE):
            with open(_MAC_CACHE_FILE) as f:
                mac = f.read().strip()
            if mac:
                return mac
    except Exception as e:
        logger.warning("could not read SmartRow MAC cache: %s", e)
    return None


def connecttosmartrow():
    logger.info("starting discovery")
    
    adapter_name = get_adapter_name_by_mac(SMARTROW_ADAPTER_MAC)
    logger.info(
        "using %s (%s) for SmartRow",
        adapter_name,
        SMARTROW_ADAPTER_MAC
    )

    # --- Fast path: SmartRow already in BlueZ device cache ---
    # Check by alias ("SmartRow") or by previously cached MAC address.
    # Only return early if BlueZ actually has the device object – if it
    # doesn't, gatt.Device.connect() will fail with "Device does not exist"
    # (BlueZ loses its device cache when the bluetooth service restarts).
    _probe = SmartRowManager(adapter_name=adapter_name)

    if not _probe.is_adapter_powered:
        logger.info("%s not powered – powering on", adapter_name)
        _probe.is_adapter_powered = True
        sleep(2)

    cached_mac = _load_smartrow_mac()
    force_scan = os.path.exists(_FORCE_SCAN_FILE)

    if force_scan:
        logger.warning(
            "SmartRow force-scan marker found — skipping BlueZ fast path"
        )
    else:
        for device in _probe.devices():
            try:
                alias = device.alias()
            except Exception:
                alias = ""

            logger.info(
                "known device: alias=%s mac=%s",
                alias,
                device.mac_address
            )

            mac_match = (
                cached_mac
                and device.mac_address.lower() == cached_mac.lower()
            )

            if alias == "SmartRow" or mac_match:
                logger.info(
                    "SmartRow already known to BlueZ: %s",
                    device.mac_address
                )
                _save_smartrow_mac(device.mac_address)
                del _probe
                return device.mac_address

    del _probe
    if cached_mac and not force_scan:
        logger.info("cached MAC %s not in BlueZ device cache – falling through to full scan", cached_mac)

    # --- Full scan: stop any stale discovery, then scan with a fresh manager ---
    # DO NOT power-cycle the adapter – on BCM43438 (Pi Zero W, UART bus) a
    # D-Bus Powered=False/True can leave the chip unresponsive until the
    # bluetooth service is restarted.  StopDiscovery + a brief pause is enough
    # to reset BlueZ's discovery state cleanly.
    try:
        _stop_probe = SmartRowManager(adapter_name=adapter_name)
        _stop_probe.stop_discovery()
        logger.info("stopped stale discovery on %s", adapter_name)
        del _stop_probe
    except Exception:
        pass
    sleep(2)  # give BlueZ time to fully process the stop before a new scan

    # Fresh manager – created after the stale session is gone so all D-Bus
    # proxy objects reflect the current adapter state.
    manager = SmartRowManager(adapter_name=adapter_name)
    logger.info("starting BLE scan on %s – pull the SmartRow handle to wake it up", adapter_name)
    manager.start_discovery()
    manager.run()

    while not manager.ready():
        sleep(0.2)

    logger.info("found SmartRow macaddress: %s", manager.smartrowmac)
    _save_smartrow_mac(manager.smartrowmac)

    if force_scan:
        try:
            os.remove(_FORCE_SCAN_FILE)
            logger.info("SmartRow force-scan marker cleared")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(
                "Could not clear SmartRow force-scan marker: %s",
                e
            )

    smartrow_mac = manager.smartrowmac

    # Explicitly stop BlueZ discovery before trying to establish
    # the SmartRow LE connection.
    try:
        manager.stop_discovery()
        logger.info(
            "stopped SmartRow discovery on %s before connection",
            adapter_name
        )
    except Exception as e:
        logger.warning(
            "could not stop SmartRow discovery on %s: %s",
            adapter_name,
            e
        )

    # Give BlueZ time to process StopDiscovery and expose the
    # discovered device to the connection manager.
    sleep(2)

    logger.info(
        "waiting for SmartRow %s to become available in BlueZ",
        smartrow_mac
    )

    return smartrow_mac
if __name__ == '__main__':

    manager = gatt.DeviceManager(adapter_name='hci1')
    device = SmartRow(mac_address="", manager=manager)
    device.connect()

    manager.run()

    # manager = SmartRoweManager(adapter_name='hci0')
    # manager.start_discovery()
    # try:
    #     manager.run()
    # except KeyboardInterrupt:
    #     for device in manager.devices():
    #         if device.is_connected():
    #             device.disconnect()
    #     manager.stop()
