import threading
import time

from .. import core as perilib_core

class Stream:

    def __init__(self, port=None, parser_generator=None):
        if port is None:
            self.port = None
            self.port_info = None
        else:
            self._assign_port(port)

        self.on_rx_data = None
        self.on_tx_packet = None
        self.on_disconnect_device = None
        self.parser_generator = parser_generator
        
        # create bidirectional link from parser/generator to stream
        if self.parser_generator is not None:
            self.parser_generator.stream = self

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
            run_builtin = self.on_rx_data(data, self)

        if run_builtin != False and self.parser_generator is not None:
            # pass all incoming data to parser
            self.parser_generator.parse(data, self)

class Manager:
    
    def __init__(self):
        # these attributes may be updated by the application
        self.port_filter = None
        self.on_connect_device = None
        self.on_disconnect_device = None
        self.check_interval = 0.25
        
        # these attributes should only be read externally, not written
        self.is_running = False

        # these attributes are intended to be private
        self._port_info_list = []
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []

    def start(self):
        # don't start if we're already running
        if not self.is_running:
            self.monitor_thread = threading.Thread(target=self._watch_ports)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            self._running_thread_ident = self.monitor_thread.ident
            self.is_running = True

    def stop(self):
        # don't stop if we're not running
        if self.is_running:
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_running = False

    def remove(self, port_info):
        try:
            # manually remove a port from the list
            # (most likely in data monitor disconnection callback)
            self._port_info_list.remove(port_info)
        except ValueError as e:
            pass

    def _watch_ports(self):
        while threading.get_ident() not in self._stop_thread_ident_list:
            # build the active list of ports
            present = []
            for port_info in self._get_port_list():
                if not self.port_filter(port_info):
                    # port doesn't match filter, so skip it
                    continue

                try:
                    # find and tag this port in the current list (if present)
                    present.append(self._port_info_list.index(port_info))
                except ValueError as e:
                    # this port is not in the list, so add it now
                    # (note, new index in list is the current list length)
                    present.append(len(self._port_info_list))
                    self._port_info_list.append(port_info)

                    # trigger the connection callback
                    self._on_connect_device(port_info)

            # remove any from the previous list that aren't in the new list and
            # trigger the disconnection callback (only necessary for devices
            # that are known but have no open data streams, since otherwise the
            # stream itself will raise an exception while waiting for new data
            # when the disconnection occurs)
            offset = 0
            for index, port_info in enumerate(self._port_info_list):
                if index not in present:
                    # trigger the disconnection callback
                    self._on_disconnect_device(port_info)

                    # remove this port from the list
                    del self._port_info_list[index - offset]

                    # increment the index offset in case multiple ports disappeared
                    offset += 1

            # wait before checking again
            time.sleep(self.check_interval)

        # remove ID from "terminate" list since we're about to end execution
        self._stop_thread_ident_list.remove(threading.get_ident())

    def _on_connect_device(self, port_info):
        run_builtin = True
        if self.on_connect_device is not None:
            # trigger the app-level connection callback
            run_builtin = self.on_connect_device({"port_info": port_info})

        # derived Manager classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically

    def _on_disconnect_device(self, port_info):
        run_builtin = True
        if self.on_disconnect_device is not None:
            # trigger the app-level disconnection callback
            run_builtin = self.on_disconnect_device({"port_info": port_info})

        # derived Manager classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically
