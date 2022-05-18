import time

from .common import *

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

    MANAGER_THREADING = 1
    STREAM_THREADING = 2
    PARSER_THREADING = 4

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

    def process(self, mode=ProcessMode.BOTH, force=False):
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
        if mode in [ProcessMode.SELF, ProcessMode.BOTH] \
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
                if self.device_filter is not None and not self.device_filter(device):
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
        if mode in [ProcessMode.BOTH, ProcessMode.SUBS]:
            for device_id in list(self.devices.keys()):
                self.devices[device_id].process(mode=ProcessMode.BOTH, force=force)

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
            self.process(ProcessMode.BOTH if ((self.threading_flags & Manager.STREAM_THREADING) != 0) else ProcessMode.SELF)

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
