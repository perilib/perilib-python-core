from .UartStream import *
from ..Exceptions import *
from ..Manager import *
from ..StreamDevice import *
from ..StreamParserGenerator import *
from ..StreamProtocol import *

class UartManager(Manager):
    """Serial device manager for abstracting stream and parser management.

    This class implements a comprehensive management layer on top of devices,
    streams, protocols, and parser/generator instances. While parent application
    code can manage these things independently, this code wraps everything into
    a single interface to handle filtered device connection monitoring, data
    stream control, packet parsing based on an externally defined protocol, and
    various types of error detection.

    For many applications, the manager layer is the only one that will have to
    be configured during initialization, and all lower-level interaction can be
    left to the manager instance."""

    AUTO_OPEN_NONE = 0
    AUTO_OPEN_SINGLE = 1
    AUTO_OPEN_ALL = 2

    def __init__(self,
            device_class=StreamDevice,
            stream_class=UartStream,
            parser_generator_class=StreamParserGenerator,
            protocol_class=StreamProtocol):
        """Initializes a serial manager instance.

        :param device_class: Class to use when instantiating new device objects
            upon connection
        :type device_class: SerialDevice

        :param stream_class: Class to use when instantiating new stream objects
            upon connection
        :type stream_class: UartStream

        :param parser_generator_class: Class to use when instantiating new
            parser/generator objects associated with new streams
        :type parser_generator_class: StreamParserGenerator

        :param protocol_class: Class to use for assigning a protocol to new
            parser/generator objects associated with new streams
        :type protocol_class: StreamProtocol

        The manager coordinates all necessary connections between a device,
        stream, and parser/generator. In the Python implementation, it also
        handles monitoring device connections and disconnections, especially in
        the case of USB devices that may be inserted or unplugged at any time.
        This is done using PySerial as a driver for device detection.

        Unlike most of the overridden methods in this child class, this one runs
        the parent (super) class method first.
        """

        # run parent constructor
        super().__init__()

        # these attributes may be updated by the application
        self.port_info_filter = None
        self.device_class = device_class
        self.stream_class = stream_class
        self.parser_generator_class = parser_generator_class
        self.protocol_class = protocol_class
        self.on_connect_device = None
        self.on_disconnect_device = None
        self.on_open_stream = None
        self.on_close_stream = None
        self.on_open_error = None
        self.on_rx_data = None
        self.on_tx_data = None
        self.on_rx_packet = None
        self.on_tx_packet = None
        self.on_rx_error = None
        self.on_incoming_packet_timeout = None
        self.on_waiting_packet_timeout = None
        self.auto_open = UartManager.AUTO_OPEN_NONE

        # these attributes are intended to be read-only
        self.streams = {}

        # these attributes are intended to be private
        self._recently_disconnected_devices = []

    def _get_connected_devices(self) -> dict:
        """Gets a collection of all currently connected serial devices.

        :returns: Dictionary of connected devices (keys are device names)
        :rtype: dict

        The set of detected devices is merged with previously known devices
        before being returned, so that devices that may have been modified in
        some way (e.g. stream attached and/or opened) will retain their state.
        Previously unknown devices are instantiated immediately, while known
        devices are reused from their previous position in the internal device
        list."""

        connected_devices = {}
        for port_info in serial.tools.list_ports.comports():
            if port_info.device in self._recently_disconnected_devices:
                # skip reporting this device for one iteration (works around rare
                # but observed case where Windows shows a device as being still
                # connected when a serial read operation has already thrown an
                # exception due to an unavailable pipe)
                continue
            if port_info.device in self.devices:
                # use existing device instance
                connected_devices[port_info.device] = self.devices[port_info.device]
            else:
                # create new device and stream instance

                # apply filter, skip if it doesn't pass
                if self.port_info_filter is not None and not self.port_info_filter(port_info):
                    continue

                # make sure the application provided everything necessary
                if self.stream_class == None:
                    raise PerilibHalException("Manager cannot attach stream without defined stream_class attribute")

                # create and configure data stream object
                stream = self.stream_class()
                stream.on_disconnect_device = self._on_disconnect_device # use internal disconnection callback
                stream.on_open_stream = self.on_open_stream
                stream.on_close_stream = self.on_close_stream
                stream.on_open_error = self.on_open_error
                stream.on_rx_data = self.on_rx_data
                stream.on_tx_data = self.on_tx_data

                # create and attach PySerial port instance to stream (not opened yet)
                stream.port = serial.Serial()
                stream.port.port = port_info.device
                stream.port_info = port_info

                # create device with stream attached
                device = self.device_class(port_info.device, stream)

                # add reference from stream back up to device for convenience
                stream.device = device

                # add device and stream to internal tables for management
                self.streams[port_info.device] = stream
                connected_devices[port_info.device] = device

        # clean out list of recently disconnected devices
        del self._recently_disconnected_devices[:]

        # send back the list of currently connected devices
        return connected_devices

    def _on_connect_device(self, device) -> None:
        """Handles serial device connections.

        :param device: Device that has just been connected
        :type device: SerialDevice

        When the connection watcher method detects a new device, that device is
        passed to this method for processing. This implementation performs auto
        opening if configured (either for the first device or for every device),
        including the creation and attachment of stream and parser/generator
        objects as required. Standard objects are used for this purpose unless
        custom classes are assigned in the relevant manager attributes."""

        run_builtin = True
        if self.on_connect_device is not None:
            # trigger the app-level connection callback
            run_builtin = self.on_connect_device(device)

        if run_builtin != False and self.auto_open != UartManager.AUTO_OPEN_NONE and self.stream_class is not None:
            # open the stream if configured to do so
            open_stream = False
            if self.auto_open == UartManager.AUTO_OPEN_ALL:
                # every connection opens a new stream
                open_stream = True
            if self.auto_open == UartManager.AUTO_OPEN_SINGLE:
                # check whether we're already monitoring a stream
                if len(self.devices) == 1:
                    # open this stream only (first connected device)
                    open_stream = True

            if open_stream == True:
                # create and configure parser/generator object if protocol is available
                if self.protocol_class != None:
                    parser_generator = self.parser_generator_class(protocol_class=self.protocol_class, stream=self.streams[device.id])
                    parser_generator.on_rx_packet = self.on_rx_packet
                    parser_generator.on_tx_packet = self.on_tx_packet
                    parser_generator.on_rx_error = self.on_rx_error
                    parser_generator.on_incoming_packet_timeout = self.on_incoming_packet_timeout
                    parser_generator.on_waiting_packet_timeout = self.on_waiting_packet_timeout
                    self.streams[device.id].parser_generator = parser_generator

                try:
                    # open the data stream
                    self.streams[device.id].open()
                except serial.serialutil.SerialException as e:
                    # unable to open the port, but don't crash
                    pass

    def _on_disconnect_device(self, device) -> None:
        """Handles device disconnections.

        :param device: Device that has just been disconnected
        :type device: SerialDevice

        When the connection watcher method detects a removed device, that device
        is passed to this method for processing. This implementation handles
        automatic closing and removal of a data stream (if one is attached), and
        resumes monitoring in the case of auto-open-first configuration."""

        # mark as recently disconnected
        self._recently_disconnected_devices.append(device.id)

        # close and remove stream if it is open and/or just present
        if device.id in self.streams:
            self.streams[device.id].close()
            del self.streams[device.id]

        run_builtin = True
        if self.on_disconnect_device is not None:
            # trigger the app-level disconnection callback
            run_builtin = self.on_disconnect_device(device)

        # remove the device itself from our list
        del self.devices[device.id]
