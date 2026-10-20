import logging
import struct

import gatt
import threading
from time import sleep
import time
from copy import deepcopy

from . import smartrowreader

logger = logging.getLogger(__name__)

SMARTROW_IDLE_TIMEOUT = 10 * 60

class DataLogger():

    ENERGIE_KCAL_MESSAGE = "a"
    WORK_STROKE_LENGTH_MESSAGE = "b"
    POWER_MESSAGE = "c"
    STROKE_RATE_STROKE_COUNT_MESSAGE = "d"
    PACE_MESSAGE = "e"
    FORCE_MESSAGE = "f"
    FIRST_PART_FORCE_CURVE_MESSAGE = "x"
    SECOND_PART_FORCE_CURVE_MESSAGE = "y"
    THIRD_PARD_FORCE_CURVE_MESSAGE = "z"

    def __init__(self, rower_interface):
        self._rower_interface = rower_interface
        self._rower_interface.register_callback(self.on_row_event)

        self.WRValues_rst = None
        self.WRValues = None
        self.WRValues_standstill = None
        self.starttime = None
        self.fullstop = None
        self.SmartRowHalt = None
        self.last_activity = time.monotonic()
        self._last_activity_distance = 0

        self._reset_state()

    def _reset_state(self):
        self.WRValues_rst = {
            'stroke_rate': 0,
            'total_strokes': 0,
            'total_distance_m': 0,
            'instantaneous pace': 0,
            'speed': 0,
            'watts': 0,
            'total_kcal': 0,
            'total_kcal_hour': 0,
            'total_kcal_min': 0,
            'heart_rate': 0,
            'elapsedtime': 0.0,
            'work': 0,
            'stroke_length': 0,
            'force': 0,
            'watts_avg':0,
            'pace_avg':0
        }
        self.WRValues = deepcopy(self.WRValues_rst)
        self.WRValues_standstill = deepcopy(self.WRValues_rst)
        self.starttime = None # time.time() # was None
        self.fullstop = True
        self.SmartRowHalt = False
        self.Initial_reset = False


    def elapsedtime(self):
        if self.fullstop == False:
            elaspedtimecalc = int(time.time() - self.starttime)
            self.WRValues.update({'elapsedtime':elaspedtimecalc})
        elif self.fullstop == True and self.WRValues.get('total_distance_m') !=0 and self.Initial_reset == True:
            if not self.starttime:
                   self.starttime = time.time()
            elaspedtimecalc = int(time.time() - self.starttime)
            self.WRValues.update({'elapsedtime':elaspedtimecalc})
        else:
            self.WRValues.update({'elapsedtime': 0})

    def on_row_event(self, event):
        if not event:
            logger.warning("Ignoring empty SmartRow event")
            return

        # Minimum expected length for each SmartRow message type.
        min_lengths = {
            self.ENERGIE_KCAL_MESSAGE: 10,
            self.WORK_STROKE_LENGTH_MESSAGE: 14,
            self.POWER_MESSAGE: 14,
            self.STROKE_RATE_STROKE_COUNT_MESSAGE: 13,
            self.PACE_MESSAGE: 12,
            self.FORCE_MESSAGE: 12,
        }

        message_type = event[0]

        ignored_message_types = {
            self.FIRST_PART_FORCE_CURVE_MESSAGE,
            self.SECOND_PART_FORCE_CURVE_MESSAGE,
            self.THIRD_PARD_FORCE_CURVE_MESSAGE,
        }

        if message_type in ignored_message_types:
            return

        if message_type not in min_lengths:
            logger.warning(
                "Ignoring unknown SmartRow event: %r",
                event
            )
            return

        if len(event) < min_lengths[message_type]:
            logger.warning(
                "Ignoring malformed SmartRow event: %r (length=%d, expected>=%d)",
                event,
                len(event),
                min_lengths[message_type]
            )
            return

        if event[0] == self.ENERGIE_KCAL_MESSAGE:
            event = event.replace(" ", "0")
            self.WRValues.update({'total_distance_m': int((event[1:6]))})
            self.WRValues.update({'total_kcal': int((event[6:10]))})
            self.elapsedtime()

        if event[0] == self.WORK_STROKE_LENGTH_MESSAGE:
            event = event.replace(" ", "0")
            #print(event)
            self.WRValues.update({'total_distance_m': int((event[1:6]))})
            self.WRValues.update({'work': float(event[7:11])/10})
            self.WRValues.update({'stroke_length': int((event[11:14]))})
            self.elapsedtime()

        if event[0] == self.POWER_MESSAGE:
            event = event.replace(" ", "0")
            self.WRValues.update({'total_distance_m': int((event[1:6]))})
            if self.SmartRowHalt == True:
                self.WRValues.update({'watts': 0})
            else:
                self.WRValues.update({'watts': int((event[6:9]))})
            self.WRValues.update({'watts_avg': float((event[9:14]))/10})
            self.elapsedtime()

        if event[0] == self.STROKE_RATE_STROKE_COUNT_MESSAGE:
            event = event.replace(" ", "0")
            self.WRValues.update({'total_distance_m': int((event[1:6]))})
            if self.SmartRowHalt == True:
                self.WRValues.update({'stroke_rate': 0})
            else:
                self.WRValues.update({'stroke_rate': float((event[6:8]))*2})
            try:
                self.WRValues.update({'total_strokes': int((event[9:13]))})
            except ValueError:
                logger.warning("STROKE_RATE_MESSAGE: could not parse total_strokes from %r", event[9:13])
            self.elapsedtime()

        if event[0] == self.PACE_MESSAGE:
            event = event.replace(" ", "0")
            self.WRValues.update({'total_distance_m': int((event[1:6]))})
            pace_inst = int(event[6])*60 + int(event[7:9])
            if self.SmartRowHalt == True:
                self.WRValues.update({'instantaneous pace': 0})
                self.WRValues.update({'speed': 0})
            else:
                self.WRValues.update({'instantaneous pace': pace_inst})
                if pace_inst != 0:
                    speed = int(500 * 100 / pace_inst) # speed in cm/s
                    self.WRValues.update({'speed': speed})
                else:
                    self.WRValues.update({'speed': 0})
            pace_avg = int(event[9])*60 + int(event[10:12])
            self.WRValues.update({'pace_avg': pace_avg})
            self.elapsedtime()

        if event[0] == self.FORCE_MESSAGE:
            event = event.replace(" ", "0")
            self.WRValues.update({'total_distance_m': int((event[1:6]))})
            if event[11] == "!":
                self.WRValues.update({'force': 0})
                self.SmartRowHalt = True
                self.fullstop = True
            else:
                self.WRValues.update({'force': int((event[7:11]))})
                if self.starttime == None:
                    self.starttime = time.time()
                    self.SmartRowHalt = False
                    self.fullstop = False
                else:
                    self.SmartRowHalt = False
                    self.fullstop = False
            self.elapsedtime()

        current_distance = self.WRValues.get('total_distance_m', 0)

        if current_distance > self._last_activity_distance:
            self.last_activity = time.monotonic()
            self._last_activity_distance = current_distance

        logger.debug(self.WRValues)


def connectSR(manager,smartrow):
    smartrow.connect()
    manager.run()

def reset(smartrow):
    smartrow.characteristic_write_value(struct.pack("<b", 13))
    sleep(0.002)
    smartrow.characteristic_write_value(struct.pack("<b", 86))
    sleep(0.002)
    smartrow.characteristic_write_value(struct.pack("<b", 64))
    sleep(0.002)
    smartrow.characteristic_write_value(struct.pack("<b", 13))

def heartbeat(sr, stop_event):
    while not stop_event.is_set():
        try:
            sr.characteristic_write_value(struct.pack("<b", 36))
        except Exception as e:
            logger.debug("SmartRow heartbeat write failed: %s", e)

        stop_event.wait(1)

def main(in_q, ble_out_q, ant_out_q, metrics_out_q=None):
    adapter_name = smartrowreader.get_adapter_name_by_mac(
        smartrowreader.SMARTROW_ADAPTER_MAC
    )

    logger.info(
        "using %s for SmartRow connection",
        adapter_name
    )

    # Keep one DataLogger for the lifetime of this PiRowFlo process.
    # A new SmartRow object is attached after every wake-up so the
    # current workout values survive a temporary BLE disconnect.
    SRtoBLEANT = None
    first_connection = True

    while True:
        logger.info(
            "WAITING_FOR_SMARTROW - waiting for SmartRow to become available"
        )

        # connecttosmartrow() performs discovery if necessary and blocks
        # until SmartRow is visible.
        macaddresssmartrower = smartrowreader.connecttosmartrow()

        # Always use fresh GATT objects for a new connection.
        manager = gatt.DeviceManager(adapter_name=adapter_name)
        smartrow = smartrowreader.SmartRow(
            mac_address=macaddresssmartrower,
            manager=manager
        )

        if SRtoBLEANT is None:
            SRtoBLEANT = DataLogger(smartrow)
        else:
            # Preserve workout/session values but receive future SmartRow
            # events from the newly-created BLE device.
            SRtoBLEANT._rower_interface = smartrow
            smartrow.register_callback(SRtoBLEANT.on_row_event)

        BC = threading.Thread(
            target=connectSR,
            args=(manager, smartrow)
        )
        BC.daemon = True
        BC.start()

        logger.info(
            "SmartRow connection attempt started"
        )

        while not smartrow.ready():
            with smartrow.lock:
                failed = smartrow.connection_failed_permanently

            if failed:
                logger.error(
                    "SmartRow connection setup failed permanently - "
                    "ending SmartRow thread for Supervisor recovery"
                )
                return

            sleep(0.2)

        logger.info("SmartRow connected and ready")
        SRtoBLEANT.last_activity = time.monotonic()
        SRtoBLEANT._last_activity_distance = (
            SRtoBLEANT.WRValues.get('total_distance_m', 0)
        )
        logger.info("starting heart beat")

        heartbeat_stop = threading.Event()

        HB = threading.Thread(
            target=heartbeat,
            args=(smartrow, heartbeat_stop)
        )
        HB.daemon = True
        HB.start()

        if first_connection:
            sleep(3)
            reset(smartrow)
            sleep(1)
            SRtoBLEANT.Initial_reset = True
            first_connection = False
        else:
            logger.info(
                "SmartRow woke up and reconnected - preserving session state"
            )

        while True:
            with smartrow.lock:
                failed = smartrow.connection_failed_permanently
                waiting = smartrow.waiting_for_wakeup

            if waiting:
                logger.info(
                    "SmartRow entered waiting-for-wakeup state - "
                    "stopping heartbeat"
                )

                heartbeat_stop.set()
                HB.join(timeout=2)

                if HB.is_alive():
                    logger.warning(
                        "SmartRow heartbeat did not stop within 2 seconds"
                    )
                else:
                    logger.info("SmartRow heartbeat stopped")

                # The manager's GLib loop should already have stopped via
                # disconnect_succeeded(), but wait briefly for its thread
                # before creating fresh GATT objects.
                BC.join(timeout=2)

                if BC.is_alive():
                    logger.warning(
                        "Old SmartRow connection thread is still running"
                    )
                else:
                    logger.info(
                        "Old SmartRow connection thread stopped"
                    )

                try:
                    manager.remove_device(smartrow.mac_address)
                    logger.info(
                        "Removed sleeping SmartRow from BlueZ cache [%s]",
                        smartrow.mac_address
                    )
                except Exception as e:
                    logger.warning(
                        "Could not remove sleeping SmartRow from BlueZ cache [%s]: %s",
                        smartrow.mac_address,
                        e
                    )
                try:
                    with open(smartrowreader._FORCE_SCAN_FILE, 'w') as f:
                        f.write(smartrow.mac_address)

                    logger.info(
                        "SmartRow wake-up scan requested"
                    )
                except Exception as e:
                    logger.warning(
                        "Could not request SmartRow wake-up scan: %s",
                        e
                    )

                logger.info(
                    "WAITING_FOR_SMARTROW - SmartRow may sleep now"
                )

                # Break only the active-session loop. The outer loop starts
                # discovery and waits for SmartRow to advertise after wake-up.
                break

            if failed:
                heartbeat_stop.set()
                HB.join(timeout=2)

                logger.error(
                    "SmartRow connection lost unexpectedly - "
                    "ending SmartRow thread for Supervisor recovery"
                )
                return

            idle_seconds = (
                time.monotonic() - SRtoBLEANT.last_activity
            )

            if idle_seconds >= SMARTROW_IDLE_TIMEOUT:
                logger.info(
                    "SmartRow inactive for %.0f seconds - "
                    "disconnecting to allow sleep",
                    idle_seconds
                )

                heartbeat_stop.set()
                HB.join(timeout=2)

                if HB.is_alive():
                    logger.warning(
                        "SmartRow heartbeat did not stop before idle disconnect"
                    )
                else:
                    logger.info(
                        "SmartRow heartbeat stopped for idle disconnect"
                    )

                try:
                    smartrow.disconnect()
                    logger.info(
                        "SmartRow idle disconnect requested"
                    )
                except Exception as e:
                    logger.warning(
                        "Could not disconnect idle SmartRow: %s",
                        e
                    )

                sleep(1)
                continue

            if not in_q.empty():
                ResetRequest_ble = in_q.get()

                if (
                    isinstance(ResetRequest_ble, str)
                    and ResetRequest_ble.startswith("hr ")
                ):
                    try:
                        SRtoBLEANT.WRValues.update({
                            'heart_rate':
                                int(ResetRequest_ble.split()[1])
                        })
                    except (ValueError, IndexError):
                        pass
                else:
                    reset(smartrow)

            ble_out_q.append(SRtoBLEANT.WRValues)
            ant_out_q.append(SRtoBLEANT.WRValues)
            if metrics_out_q is not None:
                metrics_out_q.append(deepcopy(SRtoBLEANT.WRValues))

            sleep(0.1)

if __name__ == '__main__':
    main()
