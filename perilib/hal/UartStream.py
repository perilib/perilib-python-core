import serial
import serial.tools.list_ports

from ..Stream import *
#from ..StreamDevice import *
#from ..StreamParserGenerator import *
#from ..StreamProtocol import *

class UartStream(Stream):
    """Serial stream class providing a bidirectional data stream to a serial device.

    This class allows reading to and writing from a serial device, using PySerial
    as the low-level driver."""

    def __str__(self):
        """Generates the string representation of the serial stream.

        :returns: String representation of the stream
        :rtype: str
        """

        return self.port_info.device if self.port_info is not None else "unidentified stream"

    def open(self) -> bool:
        """Opens the serial stream.

        :returns: Status of open attempt
        :rtype: bool

        This opens the serial port if it is not already open."""

        # don't start if we're already running
        if not self.is_open:
            try:
                if not self.port.is_open:
                    self.port.open()
                    self._port_open = True
                if self.on_open_stream is not None:
                    # trigger application callback
                    self.on_open_stream(self)

                self.is_open = True
            except serial.serialutil.SerialException as e:
                if self.on_open_error is not None:
                    # trigger application callback
                    self.on_open_error(self, e)

        return self.is_open

    def close(self) -> bool:
        """Closes the serial stream.

        :returns: Status of close attempt
        :rtype: bool

        This closes the serial port if it is currently open."""

        # don't close if we're not open
        if self.is_open:
            # trigger appropriate closure/disconnection callbacks
            self._cleanup_port_closure()
            return True

        # already closed if we got here
        return False

    def write(self, data) -> int:
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

    def process(self, mode=ProcessMode.BOTH, force=False) -> None:
        """Handle any pending events or data waiting to be processed.

        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy (parser/generator
            objects in this case), or both
        :type mode: int

        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool

        This method must be executed inside of a constant event loop to step
        through all necessary checks and trigger any relevant data processing
        and callbacks. Calling this method will automatically call it on all
        associated parser/generator objects."""

        try:
            # check for available data
            if mode in [ProcessMode.SELF, ProcessMode.BOTH] \
                    and self.is_open \
                    and self.port.is_open \
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

    def _cleanup_port_closure(self) -> None:
        """Handle a closed port cleanly.

        A serial port may close due to device removal (unexpected) or due to
        stream closure (expected). In either case, the internal port closure
        status value is updated here, and in the case of an unexpected closure,
        the device disconnection callback is triggered."""

        # mark data stream publicly closed
        self.is_open = False

        if self.on_close_stream is not None:
            # trigger port closure callback
            self.on_close_stream(self)

        # close the port now if necessary (indicates device removal if so)
        if self._port_open:
            try:
                # might fail due if the underlying port is already closed
                self.port.close()
            except (OSError, serial.serialutil.SerialException) as e:
                # silently ignore failures to close the port, but that means the device is gone
                if self.on_disconnect_device:
                    # trigger application callback
                    self.on_disconnect_device(self.device)
            finally:
                # mark port privately closed
                self._port_open = False
