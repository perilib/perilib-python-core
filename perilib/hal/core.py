import threading
import time

from .. import core as perilib_core

class Device:
    """Base device class to be used by Manager objects.
    
    This class represents a single connected device, typically available via a
    COMx port (Windows) or /dev/tty* on Linux or macOS. It could also be a HID
    object or anything else uniquely identifiable and detected by a subclass."""
    
    def __init__(self, id, port=None, stream=None):
        """Initializes a device instance.
        
        The ID of the device is requires, while the port and stream may be
        omitted."""
        
        self.id = id
        self.port = port
        self.stream = stream
    
    def __str__(self):
        """Generates the string representation of the device.
        
        This basic implementation simply uses the string representation of the
        assigned ID attribute."""
        
        return str(self.id)

class Stream:
    """Base stream class to manage bidirectional data streams.
    
    This class represents a data stream and is optionally associated with a
    device and/or a parser/generator object to manage connectivity monitoring
    and protocol decoding/encoding. However, it is fundamentally separate from
    these higher and lower layers in the communication stack, and internally
    manages only receiption and transmission of data. It spawns a dedicated
    thread to monitor for incoming data, allowing the main application thread
    to continue executing without blocking."""

    def __init__(self, device=None, parser_generator=None):
        self.device = device
        self.parser_generator = parser_generator
        
        self.on_open_stream = None
        self.on_close_stream = None
        self.on_rx_data = None
        self.on_tx_data = None
        self.on_disconnect_device = None
        
        self.is_open = False

        self._port_open = False
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []

    def __str__(self):
        return str(self.device)

    def open(self):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented open() method, cannot use base class stub")

    def close(self):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented close() method, cannot use base class stub")

    def write(self, data):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented write() method, cannot use base class stub")

    def _watch_data(self):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented _watch_data() method, cannot use base class stub")

    def _on_rx_data(self, data):
        # child class may re-implement
        run_builtin = True
        if self.on_rx_data:
            run_builtin = self.on_rx_data(data, self)
            
        # derived Stream classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically
            
class Manager:
    """Base manager class to coordinate device connectivity monitoring.
    
    This class provides a framework for detecting new device connections as well
    as disconnections of previously visible devices. It also provides a generic
    mechanism for filtering devices that may be interesting to the appliction,
    although the specific application of this filter depends on the interface
    that is used to detect and obtain information about connected devices (such
    as serial ports or HID entities).
    
    This class should not be used directly, but rather used as a base for child
    classes that use specific low-level communication drivers. As a minimum, a
    child class must implement the _get_connected_devices() method."""
    
    def __init__(self):
        # these attributes may be updated by the application
        self.device_filter = None
        self.on_connect_device = None
        self.on_disconnect_device = None
        self.check_interval = 0.25
        
        # these attributes should only be read externally, not written
        self.is_running = False
        self.devices = {}

        # these attributes are intended to be private
        self._monitor_thread = None
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []

    def start(self):
        # don't start if we're already running
        if not self.is_running:
            self._monitor_thread = threading.Thread(target=self._watch_devices)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            self._running_thread_ident = self._monitor_thread.ident
            self.is_running = True

    def stop(self):
        # don't stop if we're not running
        if self.is_running:
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_running = False

    def _get_connected_devices(self):
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented _get_connected_devices() method, cannot use base class stub")

    def _watch_devices(self):
        while threading.get_ident() not in self._stop_thread_ident_list:
            # assume every previously connected device is no longer connected
            ids_to_disconnect = list(self.devices.keys())

            # build the active list of filtered devices
            connected_devices = self._get_connected_devices()
            for device_id, device in connected_devices.items():
                # remove this device from list of assumed disconnections
                if device_id in ids_to_disconnect:
                    ids_to_disconnect.remove(device_id)
                    
                # apply filter, skip if it doesn't pass
                if not self.device_filter(device):
                    continue

                # add this device to the list if not already present
                if device_id not in self.devices:
                    self.devices[device_id] = device

                    # trigger the connection callback
                    self._on_connect_device(device)

            # disconnect devices that were there before and aren't anymore
            for device_id in ids_to_disconnect:
                if device_id in self.devices:
                    # trigger the disconnection callback
                    self._on_disconnect_device(self.devices[device_id])

                    # remove this port from the list
                    del self.devices[device_id]

            # wait before checking again
            time.sleep(self.check_interval)

        # remove ID from "terminate" list since we're about to end execution
        self._stop_thread_ident_list.remove(threading.get_ident())

    def _on_connect_device(self, device):
        run_builtin = True
        if self.on_connect_device is not None:
            # trigger the app-level connection callback
            run_builtin = self.on_connect_device(device)

        # derived Manager classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically

    def _on_disconnect_device(self, device):
        run_builtin = True
        if self.on_disconnect_device is not None:
            # trigger the app-level disconnection callback
            run_builtin = self.on_disconnect_device(device)

        # derived Manager classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically
