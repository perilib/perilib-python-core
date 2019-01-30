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
        
        The ID and port of the device are required, while the stream may be
        omitted. The port should be either an actual serial port object from
        the PySerial library (from which a ListPortInfo instance will be
        identified), or a ListPortInfo instance (from which a serial port object
        will be created)."""

        super().__init__(id, port, stream)

        if type(port) is serial.tools.list_ports_common.ListPortInfo:
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
        # don't start if we're already running
        if not self.is_open:
            if not self.device.port.is_open:
                self.device.port.open()
                self._port_open = True
            if self.on_open_stream is not None:
                # trigger application callback
                self.on_open_stream(self)
            self._monitor_thread = threading.Thread(target=self._watch_data)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            self._running_thread_ident = self._monitor_thread.ident
            self.is_open = True

    def close(self):
        # don't close if we're not open
        if self.is_open:
            if self._port_open:
                self._port_open = False
                try:
                    self.device.port.close()
                except (OSError, serial.serialutil.SerialException) as e:
                    pass
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_open = False

    def write(self, data):
        if self.on_tx_data is not None:
            # trigger application callback
            self.on_tx_data(data, self)
        return self.device.port.write(data)

    def _watch_data(self):
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

        # remove ID from "terminate" list since we're about to end execution
        self._stop_thread_ident_list.remove(threading.get_ident())

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
                    
                    # stop polling for port changes
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
                    self.streams[device.id].parser_generator = parser_generator
                
                    # start the parser/generator thread
                    self.streams[device.id].parser_generator.start()
                    
                # open the data stream
                self.streams[device.id].open()

    def _on_disconnect_device(self, device):
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
        if self.auto_open == SerialManager.AUTO_OPEN_SINGLE and len(self.devices) == 0:
            self.start()
            
    def _on_rx_data(self, data, stream):
        run_builtin = True
        if self.on_rx_data is not None:
            # trigger the app-level RX data callback
            run_builtin = self.on_rx_data(data, stream)
            
        if run_builtin != False and stream.parser_generator is not None:
            # add data to parse queue
            stream.parser_generator.queue(data)
