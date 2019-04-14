import serial
import serial.tools.list_ports
import threading

from ..Stream import *
#from ..StreamDevice import *
#from ..StreamParserGenerator import *
#from ..StreamProtocol import *

class UartStream(Stream):
    """Serial stream class providing a bidirectional data stream to a serial device.
    
    This class allows reading to and writing from a serial device, using PySerial
    as the low-level driver. It also provides a thread-based non-blocking RX data
    monitor and callback mechanism, which allows painless integration into even
    the most complex parent application logic."""

    def __str__(self):
        """Generates the string representation of the serial stream.
        
        :returns: String representation of the stream
        :rtype: str
        """

        return self.port_info.device if self.port_info is not None else "unidentified stream"

    def open(self):
        """Opens the serial stream.
        
        This opens the serial port if it is not already open, and starts an
        incoming data monitor thread to capture data from the port. This thread
        continues as long as the stream (port) remains open."""

        # don't start if we're already running
        if not self.is_open:
            if not self.port.is_open:
                self.port.open()
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
                    self.port.close()
                except (OSError, serial.serialutil.SerialException) as e:
                    pass
                    
            # stop the RX data monitoring thread (ignored if not running)
            self.stop()

    def write(self, data):
        """Writes data to the serial stream.
        
        :param data: Data buffer to be sent out to the stream
        :type data: bytes

        :returns: Number of bytes written to the stream
        :rtype: int

        This transmits data to the serial stream using the standard serial
        `write` method. The data argument should be a `bytes()` object, or
        something that can be transparently converted to a `bytes()` object."""

        if self.on_tx_data is not None:
            # trigger application callback
            self.on_tx_data(data, self)
            
        try:
            result = self.port.write(data)
        except serial.serialutil.SerialException as e:
            result = False
            
        return result

    def process(self, mode=ProcessMode.BOTH, force=False):
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
            if mode in [ProcessMode.SELF, ProcessMode.BOTH] \
                    and self.is_open \
                    and self.port.in_waiting != 0:
                # read all available data
                data = self.port.read(self.port.in_waiting)

                # pass data to internal receive callback
                self._on_rx_data(data)
                
            # allow associated parser/generator to process immediately
            if mode in [ProcessMode.BOTH, ProcessMode.SUBS]:
                if self.parser_generator is not None:
                    self.parser_generator.process(mode=ProcessMode.BOTH, force=force)
                
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
                data = self.port.read()
                if self.port.in_waiting != 0:
                    # if more data is available now, read it immediately
                    data += self.port.read(self.port.in_waiting)

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
                self.port.close()
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
