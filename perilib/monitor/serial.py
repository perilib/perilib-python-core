import serial.tools.list_ports

from . import core

class SerialMonitor(core.Monitor):

    def _get_port_list(self):
        return serial.tools.list_ports.comports()
