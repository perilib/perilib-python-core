from .Device import *

class StreamDevice(Device):
    """Stream device class representing a single connected streaming device.

    Within the Python environment, streaming devices usually use a serial
    interface (USB CDC or direct built-in RS-232 serial). However, other stream
    transports are possible."""

    def __init__(self, id, stream):
        """Initializes a serial device instance.

        :param id: An identifier given to this device, such as the port number
            it is attached to or the model number (if known ahead of time)
        :type id: str

        :param stream: Stream object which this device uses, if one exists
        :type stream: Stream

        """

        super().__init__(id)
        self.stream = stream

    def __str__(self):
        """Generates the string representation of the streaming device.

        :returns: String representation of the device
        :rtype: str

        This basic implementation simply uses the string representation of the
        assigned stream object, since it should be unique among all devices."""

        return str(self.stream)
