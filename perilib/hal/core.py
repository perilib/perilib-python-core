from .. import core as perilib_core

class Stream:

    def __init__(self, port=None, on_rx_data=None, on_tx_packet=None, on_disconnect_device=None, parser_generator=None):
        if port is None:
            self.port = None
            self.port_info = None
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
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented open() method, cannot use base class stub")

    def close(self):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented close() method, cannot use base class stub")

    def write(self, data):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented write() method, cannot use base class stub")

    def _assign_port(self, port):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented _assign_port() method, cannot use base class stub")

    def _watch_data(self):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented _assign_port() method, cannot use base class stub")

    def _on_rx_data(self, data):
        run_builtin = True

        if self.on_rx_data:
            run_builtin = self.on_rx_data(data)

        if run_builtin != False and self.parser_generator is not None:
            # pass all incoming data to parser
            self.parser_generator.parse(data, self.port_info)
