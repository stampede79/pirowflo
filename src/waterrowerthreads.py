"""
Python script to broadcast waterrower data over BLE and ANT

      PiRowFlo for Waterrower
                                                                 +-+
                                               XX+-----------------+
                  +-------+                 XXXX    |----|       | |
                   +-----+                XXX +----------------+ | |
                   |     |             XXX    |XXXXXXXXXXXXXXXX| | |
    +--------------X-----X----------+XXX+------------------------+-+
    |                                                              |
    +--------------------------------------------------------------+

To begin choose an interface from where the data will be taken from either the S4 Monitor connected via USB or
the Smartrow pulley via bluetooth low energy

Then select which broadcast methode will be used. Bluetooth low energy or Ant+ or both.

e.g. use the S4 connected via USB and broadcast data over bluetooth and Ant+

python3 waterrowerthreads.py -i s4 -b -a
"""

import socket
import os
import logging
import logging.config
import threading
import argparse
from queue import Queue
from collections import deque

from adapters.ble import waterrowerble
from adapters.s4 import wrtobleant
from adapters.ant import waterrowerant
from adapters.smartrow import smartrowtobleant
import pathlib
import signal
import json

loggerconfigpath = str(pathlib.Path(__file__).parent.absolute()) +'/' +'logging.conf'

logger = logging.getLogger(__name__)
Mainlock = threading.Lock()

CONTROL_SOCKET = "/tmp/pirowflo-control.sock"


def control_socket_server(reset_q, metrics_q):
    try:
        if os.path.exists(CONTROL_SOCKET):
            os.unlink(CONTROL_SOCKET)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(CONTROL_SOCKET)
        os.chmod(CONTROL_SOCKET, 0o600)
        server.listen(1)

        logger.info(
            "PiRowFlo control socket listening on %s",
            CONTROL_SOCKET
        )

        while True:
            conn, _ = server.accept()

            try:
                command = conn.recv(1024).decode().strip()

                if command == "reset":
                    reset_q.put("reset_ble")
                    conn.sendall(b"OK\n")
                    logger.info(
                        "Reset requested via control socket"
                    )

                elif command == "metrics":
                    if metrics_q:
                        metrics = dict(metrics_q[-1])
                    else:
                        metrics = {}

                    response = json.dumps(metrics) + "\n"
                    conn.sendall(response.encode())

                else:
                    conn.sendall(b"ERROR unknown command\n")

            finally:
                conn.close()

    except Exception:
        logger.exception(
            "PiRowFlo control socket failed"
        )

class Graceful:

    def __init__(self):
        self.run = True
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        Mainlock.acquire()
        self.run = False
        logger.info("Quit gracefully program has been interrupt externally - exiting")
        Mainlock.release()


def main(args=None):
    logging.config.fileConfig(loggerconfigpath, disable_existing_loggers=False)
    grace = Graceful()

    def BleService(out_q, ble_in_q):
        logger.info("Start BLE Advertise and BLE GATT Server")
        waterrowerble.main(out_q, ble_in_q)


    def Waterrower(in_q, ble_out_q, ant_out_q):
        logger.info("Waterrower Interface started")
        Waterrowerserial = wrtobleant.main(in_q, ble_out_q, ant_out_q)
        Waterrowerserial()

    def Smartrow(in_q, ble_out_q, ant_out_q, metrics_out_q):
        logger.info("Smartrow Interface started")
        smartrowtobleant.main(
            in_q,
            ble_out_q,
            ant_out_q,
            metrics_out_q,
        )

    def ANTService(in_q, ant_in_q):
        logger.info("Start Ant and start broadcast data")
        waterrowerant.main(in_q, ant_in_q)


    # TODO: Switch from queue to deque
    q = Queue()

    metrics_q = deque(maxlen=1)

    control_thread = threading.Thread(
        target=control_socket_server,
        args=(q, metrics_q),
        daemon=True,
    )
    control_thread.start()

    ble_q = deque(maxlen=1)
    ant_q = deque(maxlen=1)
    threads = []
    ble_thread = None
    if args.interface == "s4":
        logger.info("inferface S4 monitor will be used for data input")
        t = threading.Thread(target=Waterrower, args=(q, ble_q, ant_q))
        t.daemon = True
        t.start()
        threads.append(t)
    else:
        logger.info("S4 not selected")

    if args.interface == "sr":
        logger.info("inferface smartrow will be used for data input")
        t = threading.Thread(
            name="SmartRow",
            target=Smartrow,
            args=(q, ble_q, ant_q, metrics_q)
        )
        t.daemon = True
        t.start()
        threads.append(t)
    else:
        logger.info("sr not selected")

    if args.blue == True:
        t = threading.Thread(
            name="BLE-FTMS",
            target=BleService,
            args=(q, ble_q)
        )
        t.daemon = True
        t.start()
        threads.append(t)
        ble_thread = t
    else:
        logger.info("Bluetooth service not used")
    if args.antfe == True:
        t = threading.Thread(
            name="ANT+",
            target=ANTService,
            args=(q, ant_q)
        )
        t.daemon = True
        t.start()
        threads.append(t)
    else:
        logger.info("Ant service not used")

    while grace.run:
        for thread in threads:
            if grace.run == True:
                thread.join(timeout=10)
                if not thread.is_alive():
                    logger.error(
                        "Thread %s died - shutting down services; thread states: %s",
                        thread.name,
                        {
                            t.name: t.is_alive()
                            for t in threads
                        }
                    )
                    if ble_thread is not None:
                        logger.info("Stopping BLE service before exit")
                        waterrowerble.shutdown()

                        if ble_thread.is_alive():
                            ble_thread.join(timeout=10)

                        if ble_thread.is_alive():
                            logger.error(
                                "BLE service did not stop cleanly - refusing immediate restart"
                            )
                            return
                        else:
                            logger.info("BLE service stopped cleanly")

                    logger.info("Services stopped - exiting")
                    return

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter, )
        parser.add_argument("-i", "--interface", choices=["s4","sr"], default="s4", help="choose  Waterrower interface S4 monitor: s4 or Smartrow: sr")
        parser.add_argument("-b", "--blue", action='store_true', default=False,help="Broadcast Waterrower data over bluetooth low energy")
        parser.add_argument("-a", "--antfe", action='store_true', default=False,help="Broadcast Waterrower data over Ant+")
        args = parser.parse_args()
        logger.info(args)
        main(args)
    except KeyboardInterrupt:
        print("code has been shutdown")

