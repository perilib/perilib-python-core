import time
import struct
import threading
import collections

from ... import core as perilib_core
from .. import core as perilib_protocol_core

class StreamProtocol(perilib_protocol_core.Protocol):
    """Generic stream protocol definition.
    
    This class provides a foundation for stream-based protocols, including stub
    methods required to detect packet boundaries and instantiate new packet
    instances from incoming data. Without subclassing, this considers every new
    byte to be a new packet, which is not suitable for virtually any real use
    case. You will most likely need to implement a subclass with more specific
    boundary detection (at the very least) suitable to the specific protocol
    that is being used."""

    incoming_packet_timeout = None
    response_packet_timeout = None

    @classmethod
    def test_packet_start(cls, buffer, is_tx=False):
        return StreamParserGenerator.STATUS_IN_PROGRESS

    @classmethod
    def test_packet_complete(cls, buffer, is_tx=False):
        return StreamParserGenerator.STATUS_COMPLETE

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False):
        return StreamPacket(buffer=buffer, parser_generator=parser_generator)

    @classmethod
    def get_packet_from_name_and_args(cls, _packet_name, _parser_generator=None, **kwargs):
        raise perilib_core.PerilibProtocolException(
                "Cannot generate '%s' packet using base StreamProtocol method, "
                "no definitions available", _packet_name)

class StreamPacket(perilib_protocol_core.Packet):
    """Generic stream packet definition.
    
    This class represents a single packet in a stream-based protocol. It may be
    either an incoming or outgoing packet, and may be created either from a byte
    buffer (typically from from incoming data) or from a dictionary of payload
    and possibly header/footer values (typically for outgoing data). This may
    also be subclassed to protocol-specific packet definitions as required for
    special classification or handling."""

    TYPE_GENERIC = 0
    TYPE_STR = ["generic"]
    TYPE_ARG_CONTEXT = ["args"]

    def __init__(self, type=TYPE_GENERIC, name=None, definition=None, buffer=None, header=None, payload=None, footer=None, metadata=None, parser_generator=None):
        self.type = type
        self.name = name
        self.definition = definition
        self.buffer = buffer
        self.header = header
        self.payload = payload
        self.footer = footer
        self.metadata = metadata
        self.parser_generator = parser_generator
        
        if self.definition is not None:
            if self.name is None and "name" in self.definition:
                # use name from packet definition
                self.name = self.definition["name"]
            
            # build whatever side of the packet is still missing
            if self.buffer is not None:
                self.build_structure_from_buffer()
            elif self.header is not None or self.payload is not None or self.footer is not None:
                self.build_buffer_from_structure()

    def __getitem__(self, arg):
        return self.payload[arg]

    def __str__(self):
        s = ""
        if self.definition is None:
            s = "undefined %s packet" % self.TYPE_STR[self.type]
        else:
            s = "%s (%s): { " % (self.name, self.TYPE_STR[self.type])
            arg_values = []
            for x in self.definition[self.TYPE_ARG_CONTEXT[self.type]]:
                arg_values.append("%s: %s" % (x["name"], self.payload[x["name"]]))
            if len(arg_values) > 0:
                s += ', '.join(arg_values) + ' '
            s += "}"
        if self.parser_generator is not None and self.parser_generator.stream is not None:
            s += " via %s" % (self.parser_generator.stream)
        else:
            s += " via unidentified stream"
        return s

    def build_structure_from_buffer(self):
        # header (optional)
        if "header_args" in self.definition:
            header_packing_info = perilib_protocol_core.Protocol.calculate_packing_info(self.definition["header_args"])
            header_expected_length = header_packing_info["expected_length"]
            self.header = perilib_protocol_core.Protocol.unpack_values(
                self.buffer[:header_expected_length],
                self.definition["header_args"],
                header_packing_info
            )
        else:
            self.header = {}
            header_expected_length = 0
            
        # footer (optional)
        if "footer_args" in self.definition:
            footer_packing_info = perilib_protocol_core.Protocol.calculate_packing_info(self.definition["footer_args"])
            footer_expected_length = footer_packing_info["expected_length"]
            self.footer = perilib_protocol_core.Protocol.unpack_values(
                    self.buffer[-footer_expected_length:],
                    self.definition["footer_args"],
                    footer_packing_info)
        else:
            self.footer = {}
            footer_expected_length = 0

        # payload (required)
        payload_packing_info = perilib_protocol_core.Protocol.calculate_packing_info(self.definition[self.TYPE_ARG_CONTEXT[self.type]])
        self.payload = perilib_protocol_core.Protocol.unpack_values(
                self.buffer[header_expected_length:len(self.buffer)-footer_expected_length],
                self.definition[self.TYPE_ARG_CONTEXT[self.type]],
                payload_packing_info)

    def build_buffer_from_structure(self):
        # pack all arguments into binary buffer
        payload_packing_info = perilib_protocol_core.Protocol.calculate_packing_info(self.definition[self.TYPE_ARG_CONTEXT[self.type]])
        self.buffer = perilib_protocol_core.Protocol.pack_values(
                self.payload,
                self.definition[self.TYPE_ARG_CONTEXT[self.type]],
                payload_packing_info)

        # allow arbitrary buffer manipulation, e.g. adding headers/footers
        # (easier to re-implement just that instead of this whole method)
        self.prepare_buffer_after_building()

    def prepare_buffer_after_building(self):
        return

class StreamParserGenerator:
    """Parser/generator class for stream-based protocols.
    
    This class provides the framework for parsing (incoming) and generating
    (outgoing) packets which adhere to a stream-based protocol. Incoming data
    is parsed one byte at a time, and it is decoded based on the associated
    protocol definition. Outgoing data is similarly built from payload, header,
    and footer dictionaries using the same protocol definition.
    
    While the application layer may pass bytes to the `parse` method by hand,
    this class also implements a thread-based queue watcher to provide simple
    monitoring of incoming data (received by a Stream object) and subsequent
    triggering of an application-level callback when a packet is fully parsed.
    This allows the application to remain separated from any sort of low-level
    data stream handling, and instead react only to complete, validated packets
    as they arrive."""

    STATUS_IDLE = 0
    STATUS_STARTING = 1
    STATUS_IN_PROGRESS = 2
    STATUS_COMPLETE = 3

    def __init__(self, protocol_class=StreamProtocol, stream=None):
        # these attributes may be updated by the application
        self.protocol_class = protocol_class
        self.stream = stream
        self.on_rx_packet = None
        self.on_rx_error = None
        self.on_incoming_packet_timeout = None
        self.on_response_packet_timeout = None
        self.incoming_packet_timeout = self.protocol_class.incoming_packet_timeout
        self.response_packet_timeout = self.protocol_class.response_packet_timeout

        # these attributes should only be read externally, not written
        self.last_rx_packet = None
        self.response_pending = None
        self.is_running = False
        self.rx_deque = collections.deque()

        # these attributes are intended to be private
        self._incoming_packet_t0 = 0
        self._response_packet_t0 = 0
        self._wait_packet_event = threading.Event()
        self._wait_timed_out = False
        self._monitor_thread = None
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []

        # reset the parser explicitly
        self.reset()

    def __str__(self):
        if self.stream is not None:
            return "par/gen on %s" % self.stream
        else:
            return "par/gen on unidentified stream"

    def start(self):
        # don't start if we're already running
        if not self.is_running:
            self._monitor_thread = threading.Thread(target=self._watch_rx_queue)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            self._running_thread_ident = self._monitor_thread.ident
            self.is_running = True

    def stop(self):
        # don't stop if we're not running
        if self.is_running:
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_running = False

    def reset(self):
        self.rx_buffer = b''
        self.parser_status = StreamParserGenerator.STATUS_IDLE
        self._incoming_packet_t0 = 0
        
    def queue(self, input_data):
        if isinstance(input_data, (int,)):
            # given a single integer, so convert it to bytes first
            input_data = bytes([input_data])
        elif isinstance(input_data, (list,)):
            # given a list, so convert it to bytes first
            input_data = bytes(input_data)

        # add new data to queue
        self.rx_deque.extend(input_data)

    def parse(self, input_data):
        if isinstance(input_data, (int,)):
            # given a single integer, so convert it to bytes first
            return self.parse_byte(input_data)
        elif isinstance(input_data, (list,)):
            # given a list, so convert it to bytes first
            input_data = bytes(input_data)

        # input_data here is now a bytes(...) buffer
        for input_byte_as_int in input_data:
            self.parse_byte(input_byte_as_int)
            
    def parse_byte(self, input_byte_as_int):
            if self.parser_status == StreamParserGenerator.STATUS_IDLE:
                # not already in a packet, so run through start boundary test function
                self.parser_status = self.protocol_class.test_packet_start(bytes([input_byte_as_int]), self)

                # if we just started and there's a defined timeout, start the timer
                if self.parser_status != StreamParserGenerator.STATUS_IDLE and self.incoming_packet_timeout is not None:
                    self._incoming_packet_t0 = time.time()

            # if we are (or may be) in a packet now, process
            if self.parser_status != StreamParserGenerator.STATUS_IDLE:
                # add byte to the buffer
                self.rx_buffer += bytes([input_byte_as_int])

                # continue testing start conditions if we haven't fully started yet
                if self.parser_status == StreamParserGenerator.STATUS_STARTING:
                    self.parser_status = self.protocol_class.test_packet_start(self.rx_buffer, self)

                # test for completion conditions if we've fully started
                if self.parser_status == StreamParserGenerator.STATUS_IN_PROGRESS:
                    self.parser_status = self.protocol_class.test_packet_complete(self.rx_buffer, self)

                # process the complete packet if we finished
                if self.parser_status == StreamParserGenerator.STATUS_COMPLETE:
                    # convert the buffer to a packet
                    try:
                        self.last_rx_packet = self.protocol_class.get_packet_from_buffer(self.rx_buffer, self)

                        # reset the parser
                        self.reset()
                        
                        if self.last_rx_packet is not None:
                            release_wait_lock = False
                            if self.last_rx_packet.name == self.response_pending:
                                # cancel timer and clear pending info
                                self._response_packet_t0 = 0
                                release_wait_lock = True

                            if self.on_rx_packet:
                                # pass packet to receive callback
                                self.on_rx_packet(self.last_rx_packet)
                                
                            # fire the wait event if necessary
                            if release_wait_lock:
                                self.response_pending = None
                                self._wait_timed_out = False
                                self._wait_packet_event.set()
                    except perilib_core.PerilibProtocolException as e:
                        if self.on_rx_error is not None:
                            self.on_rx_error(e, self.rx_buffer, self)
            else:
                # still idle after parsing a byte, probably malformed/junk data
                self._incoming_packet_t0 = 0

    def generate(self, _packet_name, **kwargs):
        # args are prefixed with '_' to avoid unlikely collision with kwargs key
        return self.protocol_class.get_packet_from_name_and_args(_packet_name, self, **kwargs)

    def send_packet(self, _packet_name, **kwargs):
        # build the packet
        packet = self.generate(_packet_name=_packet_name, **kwargs)
        
        # trigger internal (and possibly external) processing callbacks
        self._on_tx_packet(packet)
        
        # transmit the data out via the stream
        result = self.stream.write(packet.buffer)
        
        # automatically set up the response timer if necessary
        if "response_required" in packet.definition:
            self.response_pending = packet.definition["response_required"]
            if self.response_pending is not None:
                self._response_packet_t0 = time.time()
                
        return result
        
    def wait_packet(self, _packet_name=None):
        # wait until we're not busy
        while self.response_pending is not None:
            if self.stream is not None and not self.stream.use_threading:
                # allow the stream to process incoming data
                self.stream.process()
        
        # check whether this is a new request ("wait for [x]") or a follow-up ("wait for whatever you have pending already")
        if _packet_name is not None:
            # abort if we're waiting already and a new packet is requested
            if self.response_pending is not None:
                return False
            else:
                # update pending packet details
                self.response_pending = _packet_name
                
                # start a new response timeout timer if necessary (only for new requests)
                self._response_packet_t0 = time.time()
        
        # don't wait if we have nothing to wait for
        if self.response_pending is not None:
            # pause execution until either success or timeout
            self._wait_packet_event.wait()
            self._wait_packet_event.clear()
                
        # return the last packet received, or None if we timed out
        return self.last_rx_packet if not self._wait_timed_out else None
        
    def send_and_wait(self, _packet_name, **kwargs):
        result = self.send_packet(_packet_name, **kwargs)
        if result != False:
            result = self.wait_packet()
        return result

    def process(self, force=False, subs=True):
        """Handle any pending events or data waiting to be processed.
        
        If the stream is being used in a non-threading arrangement, this method
        should periodically be executed to manually step through all necessary
        checks and trigger any relevant data processing and callbacks. Calling
        this method will automatically call it on an associated parser/generator
        object.
        
        This is the same method that is called internally in an infinite loop
        by the thread target, if threading is used."""
        
        # get data from queue (blocking request)
        while len(self.rx_deque) > 0:
            self.parse_byte(self.rx_deque.popleft())
        
        if self._incoming_packet_t0 != 0 and time.time() - self._incoming_packet_t0 > self.incoming_packet_timeout:
            self._incoming_packet_timed_out();

        if self._response_packet_t0 != 0 and time.time() - self._response_packet_t0 > self.response_packet_timeout:
            self._response_packet_timed_out();
        
    def _on_tx_packet(self, packet):
        if self.on_tx_packet is not None:
            # trigger application callback
            self.on_tx_packet(packet)

    def _incoming_packet_timed_out(self):
        if self.on_incoming_packet_timeout is not None:
            # pass partial packet to timeout callback
            self.on_incoming_packet_timeout(self.rx_buffer, self)

        # reset the parser
        self.reset()

    def _response_packet_timed_out(self):
        if self.on_response_packet_timeout is not None:
            # pass partial packet to timeout callback
            self.on_response_packet_timeout(self.response_pending, self)
            
        # reset the pending response
        self.response_pending = None
        self._response_packet_t0 = 0

        # fire the wait event if necessary
        self._wait_timed_out = True
        self._wait_packet_event.set()
        
    def _watch_rx_queue(self):
        while threading.get_ident() not in self._stop_thread_ident_list:
            self.process()

        # remove ID from "terminate" list since we're about to end execution
        self._stop_thread_ident_list.remove(threading.get_ident())
