import collections
import time

from .Exceptions import *
from .StreamProtocol import *

class StreamParserGenerator:
    """Parser/generator class for stream-based protocols.

    This class provides the framework for parsing (incoming) and generating
    (outgoing) packets which adhere to a stream-based protocol. Incoming data
    is parsed one byte at a time, and it is decoded based on the associated
    protocol definition. Outgoing data is similarly built from payload, header,
    and footer dictionaries using the same protocol definition.

    This allows the application to remain separated from any sort of low-level
    data stream handling, and instead react only to complete, validated packets
    as they arrive."""

    def __init__(self, protocol_class=StreamProtocol, stream=None):
        """Creates a new parser/generator instance.

        :param protocol_class: Protocol definition attached to this
                parser/generator
        :type protocol_class: StreamProtocol

        :param stream: Stream attached to this parser/generator, if any
        :type stream: Stream

        This object is one of the most important pieces of a Perilib construct,
        since it coordinates a protocol definition with incoming and outgoing
        binary data. It is possible to use this without an associated stream
        object and simply feed data in manually (and generate packets for later
        transmission by your application code), but it is simplest to provide
        both the protocol definition and an associated stream.

        Simply feed data (single bytes or as a byte array) into the parse method
        and the parser will maintain packet state information according to the
        protocol structure. Whenever relevant events occur, the appropriate
        callback (if assigned) will be triggered along with relevant data about
        that event.

        You must allow your application code to call the `process()` method
        continuously (either directly or via a stream, device, or manager higher
        up in the chain) in order to ensure timely reactions to incoming data
        and duration checks."""

        # these attributes may be updated by the application
        self.protocol_class = protocol_class
        self.stream = stream
        self.on_rx_packet = None
        self.on_tx_packet = None
        self.on_rx_error = None
        self.on_incoming_packet_timeout = None
        self.on_waiting_packet_timeout = None
        self.incoming_packet_timeout = self.protocol_class.incoming_packet_timeout
        self.waiting_packet_timeout = self.protocol_class.waiting_packet_timeout

        # these attributes should only be read externally, not written
        self.last_rx_packet = None
        self.last_tx_packet = None
        self.last_pending_packet = None
        self.packet_pending = None
        self.is_running = False
        self.rx_deque = collections.deque()

        # these attributes are intended to be private
        self._incoming_packet_t0 = 0
        self._waiting_packet_t0 = 0
        self._use_waiting_packet_timeout = 0
        self._wait_timed_out = False

        # reset the parser explicitly
        self.reset()

    def __str__(self):
        """Generates the string representation of the device.

        This simple implementation includes the string representation of the
        stream if one is attached, or else a generic description."""

        if self.stream is not None:
            return "par/gen on %s" % self.stream
        else:
            return "par/gen on unidentified stream"

    def reset(self):
        """Resets the parser to an idle/empty state.

        After a packet is parsed successfully, or if a partial packet fails to
        be parsed mid-stream for some reason (e.g. malformed data or bad CRC),
        this method resets relevant buffer, state, and timeout properties to
        values suitable to start a new packet.

        The parser method automatically calls this method at appropriate times
        while processing incoming data, but you can also call it externally if
        necessary (though it is usually not needed)."""

        self.rx_buffer = b''
        self.parser_status = ParseStatus.IDLE
        self._incoming_packet_t0 = 0

    def queue(self, input_data):
        """Add data to the RX queue for later processing.

        :param input_data: Byte buffer to append to the parse queue
        :type input_data: bytes

        :returns: New size of queue
        :rtype: int

        This method is most appropriate within the context of concurrency.
        Incoming data is added to the queue, which is polled periodically when
        the event loop calls the `process()` method.

        Any data queued with this method will not be processed until the
        `process()` method is called, either manually from the app or
        by an external event loop."""

        if isinstance(input_data, (int,)):
            # given a single integer, so convert it to bytes first
            input_data = bytes([input_data])
        elif isinstance(input_data, (list,)):
            # given a list, so convert it to bytes first
            input_data = bytes(input_data)

        # add new data to queue
        self.rx_deque.extend(input_data)

    def parse(self, input_data, is_tx=False):
        """Parse one or more bytes of incoming data.

        :param input_data: Byte buffer to parse immediately
        :type input_data: bytes

        This method standardizes input data into a `bytes()` format, then passes
        this data one byte at a time to the `parse_byte()` method. Although you
        can use the `parse_byte()` method directly, this one allows objects of
        various types as input and is therefore the more "friendly" option."""

        if isinstance(input_data, (int,)):
            # given a single integer, so convert it to bytes first
            return self.parse_byte(input_data)
        elif isinstance(input_data, (list,)):
            # given a list, so convert it to bytes first
            input_data = bytes(input_data)

        # input_data here is now a bytes(...) buffer
        result = None
        for input_byte_as_int in input_data:
            result = self.parse_byte(input_byte_as_int, is_tx)

        # send back the last result (useful for parsing complete packets)
        return result

    def parse_byte(self, input_byte_as_int, is_tx=False):
        """Parse a byte of data according to the associated protocol definition.

        :param input_byte_as_int: Single byte to parse
        :type input_byte_as_int: int

        This is the core of the parser side of the parser/generator object. It
        processes each byte and maintains state tracking information required to
        follow the flow of incoming packets, detect timeouts, trigger important
        callbacks, and create packet instances from binary buffers.

        Depending on the current state of the parser, each new byte is tested
        for the start and/or end condition (typically supplied by the protocol
        definition class, though the start test case specifically might in some
        cases be left unchanged so that any byte indicates a new packet). Once a
        packet is successfully received and not tossed out as invalid by the
        `test_packet_complete()` callback, the binary buffer is converted to a
        full packet using the `get_packet_from_buffer()` method also in the
        protocol definition class, and finally handed to the application as a
        new packet for processing.

        Packets that are parsed according to given structural requirements but
        then not identified in the protocol will generate an error callback, as
        will packets that partially arrive but time out (if an incoming packet
        timeout is defined)."""

        # add byte to buffer (note, byte may be removed later if detected as backspace)
        self.rx_buffer += bytes([input_byte_as_int])

        if self.parser_status == ParseStatus.IDLE:
            # not already in a packet, so run through start boundary test function
            self.parser_status = self.protocol_class.test_packet_start(self.rx_buffer, self)

            # if we just started and there's a defined timeout, start the timer
            if self.parser_status != ParseStatus.IDLE and self.incoming_packet_timeout is not None:
                self._incoming_packet_t0 = time.time()

        # if we are (or may be) in a packet now, process
        if self.parser_status != ParseStatus.IDLE:
            # check for protocol-defined backspace bytes
            backspace = False
            if self.protocol_class.backspace_bytes is not None and len(self.protocol_class.backspace_bytes) > 0:
                backspace = input_byte_as_int in self.protocol_class.backspace_bytes

            if backspace:
                # remove backspace + previous byte from buffer, if possible
                if len(self.rx_buffer) > 1:
                    # buffer had data in it before
                    self.rx_buffer = self.rx_buffer[:-2]
                else:
                    # buffer had no data, so just remove the backspace
                    self.rx_buffer = self.rx_buffer[:-1]

                # check for empty buffer
                if len(self.rx_buffer) == 0:
                    self.parser_status = ParseStatus.IDLE
            else:
                # continue testing start conditions if we haven't fully started yet
                if self.parser_status == ParseStatus.STARTING:
                    self.parser_status = self.protocol_class.test_packet_start(self.rx_buffer, self)

                # test for completion conditions if we've fully started
                if self.parser_status == ParseStatus.IN_PROGRESS:
                    self.parser_status = self.protocol_class.test_packet_complete(self.rx_buffer, self)

            # process the complete packet if we finished
            if self.parser_status == ParseStatus.COMPLETE:
                # check for protocol-defined trim bytes
                if self.protocol_class.trim_bytes is not None and len(self.protocol_class.trim_bytes) > 0:
                    for b in self.protocol_class.trim_bytes:
                        if self.rx_buffer[-1] == b:
                            self.rx_buffer = self.rx_buffer[:-1]

                # convert the buffer to a packet
                try:
                    self.last_rx_packet = self.protocol_class.get_packet_from_buffer(self.rx_buffer, self, is_tx)

                    # reset the parser
                    self.reset()

                    if self.last_rx_packet is not None:
                        release_wait_lock = False
                        if self.last_rx_packet.name == self.packet_pending:
                            # cancel timer and clear pending info
                            self.last_pending_packet = self.last_rx_packet
                            self._waiting_packet_t0 = 0
                            release_wait_lock = True

                        if self.on_rx_packet:
                            # pass packet to receive callback
                            self.on_rx_packet(self.last_rx_packet)

                        # fire the wait event if necessary
                        if release_wait_lock:
                            self.packet_pending = None
                            self._wait_timed_out = False
                            self._wait_packet_event.set()

                        # just completed a packet, so return it
                        return self.last_rx_packet
                except PerilibProtocolException as e:
                    if self.on_rx_error is not None:
                        self.on_rx_error(e, self.rx_buffer, self)

                    # reset the parser
                    self.reset()
        else:
            # still idle after parsing a byte, probably malformed/junk data
            self.reset()

        # if we haven't already returned, we have nothing to return
        return None

    def generate(self, _packet_name, **kwargs):
        """Create a packet from a name and argument dictionary.

        :param _packet_name: Name of packet to create
        :type _packet_name: str

        This method is primarily useful for creating outgoing packets just prior
        to transmission. This method accepts a name and optional argument
        dictionary and passes them to the protocol class (with a copy of the
        calling parser/generator object) to be assembled into a full packet
        instance, including the associated binary buffer ready to send to a
        stream."""

        # args are prefixed with '_' to avoid unlikely collision with kwargs key
        return self.protocol_class.get_packet_from_name_and_args(_packet_name, self, **kwargs)

    def send_packet(self, _packet_name, **kwargs):
        """Send a packet out via an associated stream.

        :param _packet_name: Name of packet to create and transmit
        :type _packet_name: str

        This method first creates a packet based on a packet name and argument
        dictionary, then sends it out via the attached stream instance. If a
        response packet is required according to the protocol definition, then a
        new incoming response packet timeout detection process is started just
        after transmission."""

        # build the packet
        packet = self.generate(_packet_name=_packet_name, **kwargs)

        # trigger internal (and possibly external) processing callbacks
        self._on_tx_packet(packet)

        # transmit the data out via the stream
        result = self.stream.write(packet.buffer)

        # automatically set up the response timer if necessary
        if "response_required" in packet.definition:
            self.packet_pending = packet.definition["response_required"]
            if self.packet_pending is not None:
                self._use_waiting_packet_timeout = self.waiting_packet_timeout
                self._waiting_packet_t0 = time.time()

        return result

    def wait_packet(self, _packet_name=None, timeout=None):
        """Block until a specific packet arrives, or times out.

        :param _packet_name: Name of packet to wait for (if required)
        :type _packet_name: str

        :param timeout: Non-default timeout in seconds (optional)
        :type timeout: int

        If a packet name is not supplied, then this method will wait until any
        protocol-defined response is received, based on the last transmitted
        command packet. In this case, if there is no pending response according
        to the protocol definition, then this method will return immediately.

        For use cases where specific command-response cycles are required, or if
        you simply want to wait for a specific packet to arrive such as a
        particular event, this method does that by blocking until that happens.
        The internal `process()` method is called inside the busy-wait loop in
        order to allow processing of incoming data and timeout detection."""

        # wait until we're not busy
        while self.packet_pending is not None:
            if self.stream is not None:
                # allow the stream to process incoming data
                self.stream.process()

        # check whether this is a new request ("wait for [x]") or a follow-up ("wait for whatever you have pending already")
        if _packet_name is not None:
            # abort if we're waiting already and a new packet is requested
            if self.packet_pending is not None:
                return False
            else:
                # update pending packet details
                self.packet_pending = _packet_name

                # start a new packet timeout timer if necessary (only for new requests)
                if timeout is None:
                    self._use_waiting_packet_timeout = self.waiting_packet_timeout
                else:
                    self._use_waiting_packet_timeout = timeout
                self._waiting_packet_t0 = time.time()

                # wait for the new packet
                while self.packet_pending is not None:
                    if self.stream is not None:
                        # allow the stream to process incoming data
                        self.stream.process()

        # don't wait if we have nothing to wait for
        if self.packet_pending is not None:
            # pause execution until either success or timeout
            self._wait_packet_event.wait()
            self._wait_packet_event.clear()

        # return the last packet received, or None if we timed out
        return self.last_pending_packet if not self._wait_timed_out else None

    def send_and_wait(self, _packet_name, **kwargs):
        """Send a packet and wait for a response.

        :param _packet_name: Name of packet to wait for (if required)
        :type _packet_name: str

        This is a convenience method that combines the `send_packet()` and
        `wait_packet()` methods into a single call. Waiting only occurs if the
        packet sending process does not result in an error."""

        result = self.send_packet(_packet_name, **kwargs)
        if result != False:
            result = self.wait_packet()
        return result

    def process(self, mode=ProcessMode.BOTH, force=False):
        """Handle any pending events or data waiting to be processed.

        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy (nothing in this
            case), or both
        :type mode: int

        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool

        This method must be executed inside of a constant event loop to step
        through all necessary checks and trigger any relevant data processing
        and callbacks."""

        # get data from queue (blocking request)
        while len(self.rx_deque) > 0:
            self.parse_byte(self.rx_deque.popleft())

        if self.incoming_packet_timeout is not None and self._incoming_packet_t0 != 0 and time.time() - self._incoming_packet_t0 > self.incoming_packet_timeout:
            self._incoming_packet_timed_out();

        if self._use_waiting_packet_timeout is not None and self._waiting_packet_t0 != 0 and time.time() - self._waiting_packet_t0 > self._use_waiting_packet_timeout:
            self._response_packet_timed_out();

    def _on_tx_packet(self, packet):
        """Internal callback for when a packet is transmitted.

        :param packet: Packet that is about to be transmitted
        :type packet: Packet

        This basic implementation simply passes the packet to the application
        for observation (if the callback is defined). Subclasses may choose to
        override this to manipulate the packet in some way first, if desired."""

        if self.on_tx_packet is not None:
            # trigger application callback
            self.on_tx_packet(packet)

    def _incoming_packet_timed_out(self):
        """Internal callback for when an incoming packet times out.

        If an incoming packet times out, the parser is reset to a fresh state
        so that it is ready to begin watching for a new packet.

        Note that this only occurs if a packet is started but then does not
        arrive completely within a (non-zero) time limit specified in the
        protocol definition. This is a separate timeout value from the response
        timeout that begins after transmitting a packet."""

        if self.on_incoming_packet_timeout is not None:
            # pass partial packet to timeout callback
            self.on_incoming_packet_timeout(self.rx_buffer, self)

        # reset the parser
        self.reset()

    def _response_packet_timed_out(self):
        """Internal callback for when a pending response packet times out.

        If a transmitted packet requires a response, this callback will be
        triggered if that response does not arrive within the (non-zero) time
        limit specified in the protocol definition. The packet must arrive
        completely (not just begin) within that time limit in order to avoid
        triggering the timeout condition."""

        if self.on_waiting_packet_timeout is not None:
            # pass pending packet name to timeout callback
            self.on_waiting_packet_timeout(self.packet_pending, self)

        # reset the pending response
        self.packet_pending = None
        self._waiting_packet_t0 = 0

        # fire the wait event if necessary
        self._wait_timed_out = True
