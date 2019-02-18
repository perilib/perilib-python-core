import serial
import serial.tools.list_ports
import threading

from .. import core as perilib_core
from .. import protocol as perilib_protocol
from . import core

class SerialDevice(core.Device):
    """Serial device class representing a single connected serial device.
    
    This class makes use of PySerial to provide access to and information about
    a serial device. These are typically either built-in or connected via USB
    ports on the host."""

    def __init__(self, id, port, stream=None):
        """Initializes a serial device instance.
        
        :param id: An identifier given to this device, such as the port number
            it is attached to or the model number (if known ahead of time)
        :type id: str
        
        :param port: The port object handling the connection, (either a PySerial
            ListPortInfo object or PySerial port object)
            
        :param stream: The stream object which this device handles, if one
            exists
        :type stream: Stream

        The ID and port of the device are required, while the stream may be
        omitted. The port should be either an actual serial port object from
        the PySerial library (from which a ListPortInfo instance will be
        identified), or a ListPortInfo instance (from which a serial port object
        will be created)."""

        super().__init__(id, port, stream)

        if isinstance(port, serial.tools.list_ports_common.ListPortInfo):
            # provided port info object
            self.port = serial.Serial()
            self.port.port = port.device
            self.port_info = port
        else:
            # provided serial port object directly
            self.port_info = None
            self.port = port

            # attempt to find port info based on device name
            for port_info in serial.tools.list_ports.comports():
                if port_info.device.lower() == port.port.lower():
                    self.port_info = port_info

    def __str__(self):
        """Generates the string representation of the serial device.
        
        This basic implementation simply uses the string representation of the
        assigned port info object."""
        
        return str(self.port_info)
    
class SerialStream(core.Stream):
    """Serial stream class providing a bidirectional data stream to a serial device.
    
    This class allows reading to and writing from a serial device, using PySerial
    as the low-level driver. It also provides a thread-based non-blocking RX data
    monitor and callback mechanism, which allows painless integration into even
    the most complex parent application logic."""

    def __str__(self):
        return self.device.id

    def open(self):
        """Opens the serial stream.
        
        This opens the serial port if it is not already open, and starts an
        incoming data monitor thread to capture data from the port. This thread
        continues as long as the stream (port) remains open."""

        # don't start if we're already running
        if not self.is_open:
            if not self.device.port.is_open:
                self.device.port.open()
                self._port_open = True
            if self.on_open_stream is not None:
                # trigger application callback
                self.on_open_stream(self)
                
            if self.use_threading:
                self.start()
                
            self.is_open = True

    def close(self):
        """Closes the serial stream.
        
        This closes the serial port if it is currently open, and stops the
        incoming data monitor thread. Note that this method does *not* directly
        trigger the application-level stream closure callback (if assigned), but
        instead waits for the thread to catch the closure flag and finish its
        own execution (which triggers the callback)."""

        # don't close if we're not open
        if self.is_open:
            if self._port_open:
                self._port_open = False
                try:
                    self.device.port.close()
                except (OSError, serial.serialutil.SerialException) as e:
                    pass
                    
            # stop the RX data monitoring thread (ignored if not running)
            self.stop()

    def write(self, data):
        """Writes data to the serial stream.
        
        :param data: The data buffer to be sent out to the stream
        :type data: bytes

        This transmits data to the serial stream using the standard serial
        `write` method. The data argument should be a `bytes()` object, or
        something that can be transparently converted to a `bytes()` object."""

        if self.on_tx_data is not None:
            # trigger application callback
            self.on_tx_data(data, self)
            
        try:
            result = self.device.port.write(data)
        except serial.serialutil.SerialException as e:
            result = False
            
        return result

    def process(self, mode=core.Stream.PROCESS_BOTH, force=False):
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
        
        This is the same method that is called internally in an infinite loop
        by the thread target, if threading is used."""

        try:
            # check for available data
            if mode in [core.Stream.PROCESS_SELF, core.Stream.PROCESS_BOTH] \
                    and self.is_open \
                    and self.device.port.in_waiting != 0:
                # read all available data
                data = self.device.port.read(self.device.port.in_waiting)

                # pass data to internal receive callback
                self._on_rx_data(data)
                
            # allow associated parser/generator to process immediately
            if mode in [core.Stream.PROCESS_BOTH, core.Stream.PROCESS_SUBS]:
                if self.parser_generator is not None:
                    self.parser_generator.process(mode=core.Stream.PROCESS_BOTH, force=force)
                
        except (OSError, serial.serialutil.SerialException) as e:
            # read failed, probably port closed or device removed
            # trigger appropriate closure/disconnection callbacks
            self._cleanup_port_closure()
            
    def _watch_data(self):
        """Watches the serial stream for incoming data.
        
        To minimize CPU usage, this method attempts to read a single byte from
        the serial port with no read timeout. Once a single byte is read, it
        then checks for any remaining data in the port's receive buffer, and
        reads that in all at once. The entire blob of data is then passed to
        the internal `_on_rx_data()` method, and the to the application-level
        `on_rx_data()` callback (if assigned).
        
        If the port is unexpectedly closed, e.g. due to removal of a USB device,
        the stream closure callback is triggered, and then the disconnection
        callback is triggered (if assigned).
        """
        
        # loop until externally instructed to stop
        while threading.get_ident() not in self._stop_thread_ident_list:
            try:
                # read one byte at first, no timeout (blocking, low CPU usage)
                data = self.device.port.read()
                if self.device.port.in_waiting != 0:
                    # if more data is available now, read it immediately
                    data += self.device.port.read(self.device.port.in_waiting)

                # pass data to internal receive callback
                self._on_rx_data(data)
            except (OSError, serial.serialutil.SerialException) as e:
                # read failed, probably port closed or device removed
                if threading.get_ident() not in self._stop_thread_ident_list:
                    self._stop_thread_ident_list.append(self._running_thread_ident)

        # trigger appropriate closure/disconnection callbacks
        self._cleanup_port_closure()

        # remove ID from "terminate" list since we're about to end execution
        self._stop_thread_ident_list.remove(threading.get_ident())

    def _cleanup_port_closure(self):
        """Handle a closed port cleanly.
        
        A serial port may close due to device removal (unexpected) or due to
        stream closure (expected). In either case, the internal port closure
        status value is updated here, and in the case of an unexpected closure,
        the device disconnection callback is triggered."""
        
        if self.on_close_stream is not None:
            # trigger port closure callback
            self.on_close_stream(self)

        # close the port now if necessary (indicates device removal if so)
        if self._port_open:
            try:
                # might fail due if the underlying port is already closed
                self.device.port.close()
            except (OSError, serial.serialutil.SerialException) as e:
                # silently ignore failures to close the port
                pass
            finally:
                # mark port privately closed
                self._port_open = False
                
                # mark data stream publicly closed
                self.is_open = False

                if self.on_disconnect_device:
                    # trigger application callback
                    self.on_disconnect_device(self.device)

class SerialManager(core.Manager):
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
            device_class=SerialDevice,
            stream_class=SerialStream,
            parser_generator_class=perilib_protocol.stream.StreamParserGenerator,
            protocol_class=perilib_protocol.stream.StreamProtocol):
        """Initializes a serial manager instance.
        
        :param device_class: The class to use when instantiating new device
            objects upon connection
        :type device_class: SerialDevice

        :param stream_class: The class to use when instantiating new stream
            objects upon connection
        :type stream_class: SerialStream

        :param parser_generator_class: The class to use when instantiating new
            parser/generator objects associated with new streams
        :type parser_generator_class: StreamParserGenerator

        :param protocol_class: The class to use for assigning a protocol to new
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
        self.device_class = device_class
        self.stream_class = stream_class
        self.parser_generator_class = parser_generator_class
        self.protocol_class = protocol_class
        self.on_connect_device = None
        self.on_disconnect_device = None
        self.on_open_stream = None
        self.on_close_stream = None
        self.on_rx_data = None
        self.on_tx_data = None
        self.on_rx_packet = None
        self.on_tx_packet = None
        self.on_rx_error = None
        self.on_incoming_packet_timeout = None
        self.on_response_packet_timeout = None
        self.auto_open = SerialManager.AUTO_OPEN_NONE

        # these attributes are intended to be read-only
        self.streams = {}
        
        # these attributes are intended to be private
        self._recently_disconnected_devices = []
        
    def _get_connected_devices(self):
        """Gets a list of all currently connected serial devices.
        
        The list of detected devices is merged with previously known devices
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
                # create new device instance
                connected_devices[port_info.device] = self.device_class(port_info.device, port_info)
                
        # clean out list of recently disconnected devices
        del self._recently_disconnected_devices[:]
        
        # send back the list of currently connected devices
        return connected_devices
        
    def _on_connect_device(self, device):
        """Handles serial device connections.
        
        :param device: The device that has just been connected
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

        if run_builtin != False and self.auto_open != SerialManager.AUTO_OPEN_NONE and self.stream_class is not None:
            # open the stream if configured to do so
            open_stream = False
            if self.auto_open == SerialManager.AUTO_OPEN_ALL:
                # every connection opens a new stream
                open_stream = True
            if self.auto_open == SerialManager.AUTO_OPEN_SINGLE:
                # check whether we're already monitoring a stream
                if len(self.streams) == 0:
                    # open a new stream for just this one
                    open_stream = True
                    
                    if self.use_threading:
                        # stop port change monitor thread
                        # (NOTE: data monitor itself catches disconnection)
                        self.stop()

            if open_stream == True:
                # make sure the application provided everything necessary
                if self.stream_class == None:
                    raise perilib_core.PerilibHalException("Manager cannot auto-open stream without defined stream_class attribute")

                # create and configure data stream object
                self.streams[device.id] = self.stream_class(device=device)
                self.streams[device.id].on_disconnect_device = self._on_disconnect_device # use internal disconnection callback
                self.streams[device.id].on_open_stream = self.on_open_stream
                self.streams[device.id].on_close_stream = self.on_close_stream
                self.streams[device.id].on_rx_data = self._on_rx_data # use internal RX data callback
                self.streams[device.id].on_tx_data = self.on_tx_data
                self.streams[device.id].use_threading = True if (self.threading_flags & core.Manager.STREAM_THREADING) != 0 else False
                
                # give stream reference to device
                self.devices[device.id].stream = self.streams[device.id]
                
                # create and configure parser/generator object if protocol is available
                if self.protocol_class != None:
                    parser_generator = self.parser_generator_class(protocol_class=self.protocol_class, stream=self.streams[device.id])
                    parser_generator.on_rx_packet = self.on_rx_packet
                    parser_generator.on_tx_packet = self.on_tx_packet
                    parser_generator.on_rx_error = self.on_rx_error
                    parser_generator.on_incoming_packet_timeout = self.on_incoming_packet_timeout
                    parser_generator.on_response_packet_timeout = self.on_response_packet_timeout
                    parser_generator.use_threading = True if (self.threading_flags & core.Manager.PARGEN_THREADING) != 0 else False
                    self.streams[device.id].parser_generator = parser_generator
                
                    if parser_generator.use_threading:
                        # start the parser/generator monitoring thread
                        self.streams[device.id].parser_generator.start()
                    
                # open the data stream
                self.streams[device.id].open()

                if self.streams[device.id].use_threading:
                    # start the stream monitoring thread
                    self.streams[device.id].start()

    def _on_disconnect_device(self, device):
        """Handles device disconnections.
        
        :param device: The device that has just been disconnected
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

        # resume watching if we stopped due to AUTO_OPEN_SINGLE
        if self.use_threading and self.auto_open == SerialManager.AUTO_OPEN_SINGLE and len(self.devices) == 0:
            self.start()
            
    def _on_rx_data(self, data, stream):
        """Automatically handles incoming data from a stream.
        
        :param data: The data buffer received from the stream
        :type data: bytes

        :param stream: The stream from which the data was received
        :type stream: SerialStream

        When new data arrives into a serial stream attached to a device under
        the purview of this manager, this method automatically passes it to the
        relevant parser/generator object. The application itself could do this,
        and indeed the RX data callback on the stream can be reassigned so that
        this method is no longer used, but that partially defeats the purpose of
        the manager. The default behavior is to let the manager do all of the
        work so that the application can focus simply on handling and sending
        packets."""

        run_builtin = True
        if self.on_rx_data is not None:
            # trigger the app-level RX data callback
            run_builtin = self.on_rx_data(data, stream)
            
        if run_builtin != False and stream.parser_generator is not None:
            # add data to parse queue
            stream.parser_generator.queue(data)
