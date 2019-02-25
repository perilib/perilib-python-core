import threading
import time

from .. import core as perilib_core

class Device:
    """Base device class to be used by Manager objects.
    
    This class represents a single connected device, typically available via a
    COMx port (Windows) or /dev/tty* on Linux or macOS. It could also be a HID
    object or anything else uniquely identifiable and detected by a subclass."""
    
    PROCESS_SELF = 1
    PROCESS_SUBS = 2
    PROCESS_BOTH = 3
    
    def __init__(self, id, port=None, stream=None):
        """Initializes a device instance.
        
        :param id: An identifier given to this device, such as the port number
            it is attached to or the model number (if known ahead of time)
        :type id: str
        
        :param port: Port object handling the connection, if one exists
            (often a PySerial ListPortInfo object for serial devices)
            
        :param stream: Stream object which this device handles, if one
            exists
        :type stream: Stream
            
        The ID of the device is required, while the port and stream may be
        omitted."""
        
        self.id = id
        self.port = port
        self.stream = stream
    
    def __str__(self):
        """Generates the string representation of the device.
        
        :returns: String representation of the device
        :rtype: str
        
        This basic implementation simply uses the string representation of the
        assigned ID attribute."""
        
        return str(self.id)

    def process(self, mode=PROCESS_BOTH, force=False):
        """Handle any pending events or data waiting to be processed.
        
        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy (stream objects in
            this case), or both
        :type mode: int
        
        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool
            
        If the device is being used in a non-threading arrangement, this method
        should periodically be executed to manually step through all necessary
        checks and trigger any relevant data processing and callbacks.
        
        This is the same method that would be called internally in an infinite
        loop by the thread target, if threading is used."""
        
        if mode in [Device.PROCESS_BOTH, Device.PROCESS_SUBS]:
            if self.stream is not None:
                self.stream.process(mode=Device.PROCESS_BOTH, force=force)

class Stream:
    """Base stream class to manage bidirectional data streams.
    
    This class represents a data stream and is optionally associated with a
    device and/or a parser/generator object to manage connectivity monitoring
    and protocol decoding/encoding. However, it is fundamentally separate from
    these higher and lower layers in the communication stack, and internally
    manages only receiption and transmission of data. It spawns a dedicated
    thread to monitor for incoming data, allowing the main application thread
    to continue executing without blocking.
    
    This class should not be used directly, but rather used as a base for child
    classes that use specific low-level communication drivers. As a minimum, a
    child class must implement the `open()`, `close()`, `write()`, and
    `_watch_data()` methods."""

    PROCESS_SELF = 1
    PROCESS_SUBS = 2
    PROCESS_BOTH = 3
    
    def __init__(self, device=None, parser_generator=None):
        """Initializes a stream instance.
        
        :param device: Device which manages this stream, if one exists
        :type device: Device
        
        :param parser_generator: Parser/generator object which this stream
            sends and receives data through, if one exists
        :type parser_generator: ParserGenerator

        A device (which has a stream) and parser/generator (which a stream has)
        may be supplied at instantiation, or later if required. A stream does
        not strictly need either of these things, but in most cases you will be
        using both, so it makes sense to provide them for reference later."""

        # these attributes may be updated by the application
        self.device = device
        self.parser_generator = parser_generator
        self.use_threading = False
        self.on_open_stream = None
        self.on_close_stream = None
        self.on_rx_data = None
        self.on_tx_data = None
        self.on_disconnect_device = None
        
        # these attributes should only be read externally, not written
        self.is_running = False
        self.is_open = False

        # these attributes are intended to be private
        self._port_open = False
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []

    def __str__(self):
        """Generates the string representation of the stream.
        
        :returns: String representation of the device
        :rtype: str

        This basic implementation simply uses the string representation of the
        assigned device. If no device is supplied, this will of course return
        the string "None" instead."""
        
        return str(self.device)

    def open(self):
        """Opens the stream.
        
        For example, a stream using PySerial as the underlying driver would use
        the `open()` method on the serial port object whenever this method is
        called.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Opening a
        stream driven by nothing at all will generate an exception."""
        
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented open() method, cannot use base class stub")

    def close(self):
        """Closes the stream.
        
        For example, a stream using PySerial as the underlying driver would use
        the `close()` method on the serial port object whenever this method is
        called.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Closing a
        stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented close() method, cannot use base class stub")

    def write(self, data):
        """Sends outgoing data to the stream.
        
        :param data: Data buffer to be sent out to the stream
        :type data: bytes

        For example, a stream using PySerial as the underlying driver would use
        the `write()` method on the serial port object whenever this method is
        called.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Writing data
        to a stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented write() method, cannot use base class stub")

    def start(self):
        """Starts monitoring for incoming data.
        
        If you have not previously configured this object to use threading,
        calling this method will enable it. If you do not want to use threading
        in your app, you should periodically call the `process()` method in a
        loop instead (either directly on the stream, or in the parent manager
        object, if one exists)."""

        # don't start if we're already running
        if not self.is_running:
            self._monitor_thread = threading.Thread(target=self._watch_data)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            self._running_thread_ident = self._monitor_thread.ident
            self.use_threading = True
            self.is_running = True

    def stop(self):
        """Stops monitoring for incoming data.
        
        If the stream was previously monitoring incoming data, this method will
        stop it. This method is automatically called if the port is closed, but
        you can also call it directly without closing the port if you wish to
        switch to non-threaded or otherwise manual data monitoring."""
        
        # don't stop if we're not running
        if self.is_running:
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_running = False
            
    def process(self, mode=PROCESS_BOTH, force=False):
        """Handle any pending events or data waiting to be processed.
        
        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy (parser/generator
            objects in this case), or both
        :type mode: int
        
        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool
            
        If the stream is being used in a non-threading arrangement, this method
        should periodically be executed to manually step through all necessary
        checks and trigger any relevant data processing and callbacks. Calling
        this method will automatically call it on an associated parser/generator
        object.
        
        This is the same method that would be called internally in an infinite
        loop by the thread target, if threading is used.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Processing a
        stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented process() method, cannot use base class stub")

    def _watch_data(self):
        """Watches the stream for incoming data.
        
        For example, a stream using PySerial as the underlying driver would use
        the `read()` method on the serial port object whenever this method is
        called.
        
        Note that this method is not intended for application use; rather, it is
        executed in a separate thread after the stream is opened in order to
        allow a non-blocking mechanism for efficient RX monitoring. If any data
        is received, this method will pass it to the `_on_rx_data()` method
        to be optionally processed and/or handed to the application-exposed
        `on_rx_data()` callback.
        
        Overridden implementations of this method should run in an infinite loop
        and safely handle any exceptions that might occur, so that the RX data
        monitoring thread will not terminate unexpectedly.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Watching data
        on a stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented _watch_data() method, cannot use base class stub")

    def _on_rx_data(self, data):
        """Handles incoming data.
        
        :param data: Data buffer that has just been received
        :type data: bytes

        When the data watcher method receives any data (one or more bytes), that
        chunk is passed to this method for processing. This simple default
        implementation merely passes it directly to the application-level data
        RX callback, if one is defined, with no additional buffering or
        processing.
        
        Child classes *may* override this implementation, but often this will
        not be necessary unless the stream itself needs extra insight into the
        data content."""

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
    child class must implement the `_get_connected_devices()` method."""
    
    PROCESS_SELF = 1
    PROCESS_SUBS = 2
    PROCESS_BOTH = 3
    
    MANAGER_THREADING = 1
    STREAM_THREADING = 2
    PARGEN_THREADING = 4
    
    def __init__(self):
        """Initializes a manager instance.
        
        The manager coordinates all necessary connections between a device,
        stream, and parser/generator. In the Python implementation, it also
        handles monitoring device connections and disconnections, especially in
        the case of USB devices that may be inserted or unplugged at any time.
        """

        # these attributes may be updated by the application
        self.device_filter = None
        self.check_interval = 1.0
        self.threading_flags = 0
        self.use_threading = False
        self.on_connect_device = None
        self.on_disconnect_device = None
        
        # these attributes should only be read externally, not written
        self.is_running = False
        self.devices = {}

        # these attributes are intended to be private
        self._monitor_thread = None
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []
        self._last_process_time = 0

    def configure_threading(self, flags):
        """Configure threading settings for this manager instance.
        
        :param flags: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy (parser/generator
            objects in this case), or both
        :type flags: int
        
        This method can set the threading use for the manager itself as well as
        for the stream(s) and parser/generator(s) lower in the hierarchy. The
        default is that streaming is not used. If threading is enabled here for
        lower objects, then it will be enabled as directed when the new objects
        are created (upon detection and opening of each stream).
        """
        
        self.threading_flags = flags
        self.use_threading = True if (self.threading_flags & Manager.MANAGER_THREADING) != 0 else False
    
    def start(self):
        """Starts monitoring for device conncecions and disconnections.
        
        The manager instance watches for connections and disconnections using
        the low-level driver (in a subclass). Either of these events will
        trigger an application-level callback with a device that triggered the
        event. If automatical connections are enabled (either for the first
        detected deivce or for all devices), then a new stream will be created
        and (if supplied) a parser/generator object attached for convenient
        handling of incoming and outgoing data.
        
        If you have not previously configured this object to use threading,
        calling this method will enable it. If you do not want to use threading
        in your app, you should periodically call the `process()` method in a
        loop instead."""

        # don't start if we're already running
        if not self.is_running:
            self._monitor_thread = threading.Thread(target=self._watch_devices)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            self._running_thread_ident = self._monitor_thread.ident
            self.use_threading = True
            self.threading_flags |= Manager.MANAGER_THREADING
            self.is_running = True

    def stop(self):
        """Stops monitoring for device connections and disconnections.
        
        If the manager was previously monitoring device connectivity, this
        method will stop it."""
        
        # don't stop if we're not running
        if self.is_running:
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_running = False

    def process(self, mode=PROCESS_BOTH, force=False):
        """Handle any pending events or data waiting to be processed.
        
        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy, or both
        :type mode: int
        
        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool
            
        If the manager is being used in a non-threading arrangement, this method
        should periodically be executed to manually step through all necessary
        checks and trigger any relevant data processing and callbacks. Calling
        this method will automatically call it on all associated device objects.
        
        This is the same method that is called internally in an infinite loop
        by the thread target, if threading is used."""

        # check for new devices on the configured interval
        t0 = time.time()
        if mode in [Manager.PROCESS_SELF, Manager.PROCESS_BOTH] \
                and (force or time.time() - self._last_process_time >= self.check_interval):
            self._last_process_time = time.time()

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
                    try:
                        del self.devices[device_id]
                    except KeyError as e:
                        # already removed, possibly from another thread
                        pass
                    
        # allow known devices to process immediately
        if mode in [Manager.PROCESS_BOTH, Manager.PROCESS_SUBS]:
            for device_id in list(self.devices.keys()):
                self.devices[device_id].process(mode=Manager.PROCESS_BOTH, force=force)
                
    def _get_connected_devices(self):
        """Gets a list of all currently connected devices.
        
        :returns: Dictionary of connected devices (keys are device names)
        :rtype: dict

        For example, a stream using PySerial as the underlying driver would use
        the `.tools.list_ports.comports()` method whenever this method is
        called.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Requesting a
        device list driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented _get_connected_devices() method, cannot use base class stub")

    def _watch_devices(self):
        """Watches the system for connections and disconnections.
        
        Note that this method is not intended for application use; rather, it is
        executed in a separate thread after the stream is opened in order to
        allow a non-blocking mechanism for efficient device monitoring. If any
        connections or disconnections are detected, this method will pass them
        to the `_on_connect_device()` or `_on_disconnect_device()` methods to be
        optionally processed and/or handed to the application-exposed
        callbacks.
        
        Overridden implementations of this method should run in an infinite loop
        and safely handle any exceptions that might occur, so that the device
        connection monitoring thread will not terminate unexpectedly.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Opening a
        stream driven by nothing at all will generate an exception."""

        while threading.get_ident() not in self._stop_thread_ident_list:
            # process self, or self+subs if threaded subs is enabled
            self.process(Manager.PROCESS_BOTH if ((self.threading_flags & Manager.STREAM_THREADING) != 0) else Manager.PROCESS_SELF)

            # wait before checking again
            time.sleep(self.check_interval)

        # remove ID from "terminate" list since we're about to end execution
        self._stop_thread_ident_list.remove(threading.get_ident())

    def _on_connect_device(self, device):
        """Handles device connections.
        
        :param device: Device that has just been connected
        :type device: Device

        When the connection watcher method detects a new device, that device is
        passed to this method for processing. This simple default implementation
        merely passes it directly to the application-level connection callback,
        if one is defined, with no additional processing.
        
        Child classes *may* override this implementation, but often this will
        not be necessary unless the manager needs extra insight into the device
        details."""

        run_builtin = True
        if self.on_connect_device is not None:
            # trigger the app-level connection callback
            run_builtin = self.on_connect_device(device)

        # derived Manager classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically

    def _on_disconnect_device(self, device):
        """Handles device disconnections.
        
        :param device: Device that has just been disconnected
        :type device: Device

        When the connection watcher method detects a removed device, that device
        is passed to this method for processing. This simple default
        implementation merely passes it directly to the application-level
        disconnection callback, if one is defined, with no additional
        processing.
        
        Child classes *may* override this implementation, but often this will
        not be necessary unless the manager needs extra insight into the device
        details."""

        run_builtin = True
        if self.on_disconnect_device is not None:
            # trigger the app-level disconnection callback
            run_builtin = self.on_disconnect_device(device)

        # derived Manager classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically
