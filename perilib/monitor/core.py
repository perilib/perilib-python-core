import threading
import time

class Monitor:

    def __init__(self, port_filter=None, on_connect_device=None, on_disconnect_device=None, check_interval=0.25, data_stream=None):
        self.port_filter = port_filter
        self.on_connect_device = on_connect_device
        self.on_disconnect_device = on_disconnect_device
        self.check_interval = check_interval
        self.data_stream = data_stream
        self.auto_open = False

        if self.data_stream is not None and self.data_stream.on_disconnect_device is None:
            self.data_stream.on_disconnect_device = self._on_disconnect_device

        self.is_running = False

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
            # trigger the user-level connection callback
            run_builtin = self.on_connect_device(port_info)

        if run_builtin != False and self.data_stream is not None and self.auto_open == True:
            # check whether we're already monitoring a serial stream
            if not self.data_stream.is_open:
                # start watching for incoming data
                self.data_stream.open(port_info)

                # stop watching for port changes
                # (NOTE: data monitor itself catches disconnection)
                self.stop()

    def _on_disconnect_device(self, port_info):
        run_builtin = True

        if self.on_disconnect_device is not None:
            # trigger the user-level disconnection callback
            run_builtin = self.on_disconnect_device(port_info)

        if run_builtin != False and self.data_stream is not None:
            # check whether this device is currently being monitored
            if self.data_stream.port_info == port_info:
                # stop the data monitor if it's still running (unlikely)
                if self.data_stream.is_open:
                    self.data_stream.close()

                # remove this port from the known device list to avoid
                # double-triggering the disconnection callback (optional)
                self.remove(port_info)

                # resume monitoring for devices
                self.start()
