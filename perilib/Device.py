from .common import *

class Device:
    """Base device class to be used by Manager objects, or directly.

    This class represents a single connected device, typically available via a
    COMx port (Windows) or /dev/tty* on Linux or macOS. It could also be a HID
    object or anything else uniquely identifiable and detected by a subclass."""

    def __init__(self, id):
        """Initializes a device instance.

        :param id: An identifier given to this device, such as the port number
            it is attached to or the model number (if known ahead of time)
        :type id: str

        The ID of the device is required, while the port and stream may be
        omitted."""

        self.id = id

    def __str__(self):
        """Generates the string representation of the device.

        :returns: String representation of the device
        :rtype: str

        This basic implementation simply uses the string representation of the
        assigned ID attribute."""

        return str(self.id)

    def process(self, mode=ProcessMode.BOTH, force=False):
        """Handle any pending events or data waiting to be processed.

        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy (stream objects in
            this case), or both
        :type mode: int

        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool

        This method must be executed inside of a constant event loop to step
        through all necessary checks and trigger any relevant data processing
        and callbacks."""

        if mode in [ProcessMode.BOTH, ProcessMode.SUBS]:
            if self.stream is not None:
                self.stream.process(mode=ProcessMode.BOTH, force=force)
