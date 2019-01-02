import serial
import threading

class SerialStream:

    def __init__(self, port=None, on_rx_data=None, on_tx_packet=None, on_disconnect_device=None, parser_generator=None):
        if port is None:
            self.port = None
        else:
            self._assign_port(port)

        self.on_rx_data = on_rx_data
        self.on_tx_packet = on_tx_packet
        self.on_disconnect_device = on_disconnect_device
        self.parser_generator = parser_generator

        self.is_open = False

        self._port_open = False
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []

    def open(self, port=None):
        # don't start if we're already running
        if not self.is_open:
            if port is not None:
                self._assign_port(port)
            if not self.port.is_open:
                self.port.open()
                self._port_open = True
            if self.on_open_stream is not None:
                # trigger port open callback
                self.on_open_stream(self.port_info)
            self._monitor_thread = threading.Thread(target=self._watch_data)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            self._running_thread_ident = self._monitor_thread.ident
            self.is_open = True

    def close(self):
        # don't close if we're not open
        if self.is_open:
            if self._port_open:
                self._port_open = False
                try:
                    self.port.close()
                except (OSError, serial.serialutil.SerialException) as e:
                    pass
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_open = False

    def write(self, data):
        return self.port.write(data)

    def send(self, _packet_name, **kwargs):
        packet = self.parser_generator.generate(_packet_name=_packet_name, _port_info=self.port_info, **kwargs)
        if self.on_tx_packet is not None:
            # trigger packet transmission callback
            self.on_tx_packet(packet)
        return self.write(packet.buffer)

    def _assign_port(self, port):
        if type(port) == serial.tools.list_ports_common.ListPortInfo:
            # provided port info object
            self.port_info = port
            self.port = serial.Serial()
            self.port.port = self.port_info.device
        else:
            # provided serial port object directly
            self.port_info = None
            self.port = port

            # attempt to find port info based on device name
            for port_info in serial.tools.list_ports.comports():
                if port_info.device.lower() == port.port.lower():
                    self.port_info = port_info

    def _watch_data(self):
        # loop until externally instructed to stop
        while threading.get_ident() not in self._stop_thread_ident_list:
            try:
                # read one byte at a time, no timeout (blocking, low CPU usage)
                data = self.port.read(1)
                if self.port.in_waiting != 0:
                    # if more data is available now, read it immediately
                    data += self.port.read(self.port.in_waiting)

                # pass data to receive callback
                self._on_rx_data(data)
            except (OSError, serial.serialutil.SerialException) as e:
                # read failed, probably port closed or device removed
                if threading.get_ident() not in self._stop_thread_ident_list:
                    self._stop_thread_ident_list.append(self._running_thread_ident)

        if self.on_close_stream is not None:
            # trigger port closure callback
            self.on_close_stream(self.port_info)

        # close the port now if necessary (indicates device removal if so)
        if self._port_open:
            try:
                # might fail due if the underlying port is already closed
                self.port.close()
            except (OSError, serial.serialutil.SerialException) as e:
                # silently ignore failures to close the port
                pass
            finally:
                # mark port closed
                self._port_open = False

                # mark stopped
                self.is_open = False

                if self.on_disconnect_device:
                    # trigger disconnection callback
                    self.on_disconnect_device(self.port_info)

        # remove ID from "terminate" list since we're about to end execution
        self._stop_thread_ident_list.remove(threading.get_ident())

    def _on_rx_data(self, data):
        run_builtin = True

        if self.on_rx_data:
            run_builtin = self.on_rx_data(data)

        if run_builtin != False and self.parser_generator is not None:
            # pass all incoming data to parser
            for in_byte in data: self.parser_generator.parse(in_byte, self.port_info)
