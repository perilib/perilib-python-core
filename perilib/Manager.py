import time

from .common import *
from .Exceptions import *

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
        self.on_connect_device = None
        self.on_disconnect_device = None

        # these attributes should only be read externally, not written
        self.is_running = False
        self.devices = {}

        # these attributes are intended to be private
        self._last_process_time = 0

    def process(self, mode=ProcessMode.BOTH, force=False):
        """Handle any pending events or data waiting to be processed.

        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy, or both
        :type mode: int

        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool

        This method must be executed inside of a constant event loop to step
        through all necessary checks and trigger any relevant data processing
        and callbacks. Calling this method will automatically call it on all
        associated device objects."""

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
                        # already removed
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
        raise PerilibHalException("Child class has not implemented _get_connected_devices() method, cannot use base class stub")


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
