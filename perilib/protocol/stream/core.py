import struct

from ... import core as perilib_core
from .. import core as perilib_protocol_core

class StreamProtocol(perilib_protocol_core.Protocol):

    rx_packet_timeout = None

    def test_packet_start(self, buffer, is_tx=False):
        return ParserGenerator.STATUS_IN_PROGRESS

    def test_packet_complete(self, buffer, is_tx=False):
        return ParserGenerator.STATUS_COMPLETE

    def get_packet_from_buffer(self, buffer, port_info=None, is_tx=False):
        return StreamPacket(buffer=buffer, port_info=port_info)

    def get_packet_from_name_and_args(self, _packet_name, _port_info, **kwargs):
        raise perilib_core.PerilibProtocolException(
                "Cannot generate '%s' packet using base StreamProtocol method, "
                "no definitions available", _packet_name)

class StreamPacket(perilib_protocol_core.Packet):

    TYPE_GENERIC = 0
    TYPE_STR = ["generic"]
    TYPE_ARG_CONTEXT = ["args"]

    def __init__(self, type=TYPE_GENERIC, name=None, definition=None, buffer=None, header=None, payload=None, footer=None, metadata=None, port_info=None):
        self.type = type
        self.name = name
        self.definition = definition
        self.buffer = buffer
        self.header = header
        self.payload = payload
        self.footer = footer
        self.metadata = metadata
        self.port_info = port_info
            
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
        if self.port_info is not None:
            s += " on %s" % (self.port_info.device)
        else:
            s += " on unidentified port"
        return s

    def build_structure_from_buffer(self):
        # assemble details for header/payload/footer args as available
        structure = {
            "header": {
                "args": self.definition["header_args"] if "header_args" in self.definition else [],
                "unpack_format": "<",
                "length": 0
            },
            "payload": {
                "args": self.definition[self.TYPE_ARG_CONTEXT[self.type]],
                "unpack_format": "<",
                "length": 0
            },
            "footer": {
                "args": self.definition["footer_args"] if "footer_args" in self.definition else [],
                "unpack_format": "<",
                "length": 0
            },
        }

        # build out unpack format string and calculate expected byte count
        for section in structure:
            for arg in structure[section]["args"]:
                structure[section]["unpack_format"] += StreamProtocol.types[arg["type"]]["pack"]
                structure[section]["length"] += StreamProtocol.types[arg["type"]]["width"]

        # combine all prescribed lengths for comparison with actual data
        packet_length = structure["header"]["length"] + structure["payload"]["length"] + structure["footer"]["length"]

        # make sure calculated lengths are sane
        if packet_length > len(self.buffer):
            raise perilib_core.PerilibProtocolException("Calculated minimum packet length %d exceeds actual packet length %d" % (packet_length, len(self.buffer)))

        # unpack all values from binary buffer
        self.header = self._unpack_arg_values(
            structure["header"]["args"],
            structure["header"]["length"],
            structure["header"]["unpack_format"],
            self.buffer[:structure["header"]["length"]]
        )
        self.payload = self._unpack_arg_values(
            structure["payload"]["args"],
            structure["payload"]["length"],
            structure["payload"]["unpack_format"],
            self.buffer[structure["header"]["length"]:len(self.buffer)-structure["footer"]["length"]]
        )
        self.footer = self._unpack_arg_values(
            structure["footer"]["args"],
            structure["footer"]["length"],
            structure["footer"]["unpack_format"],
            self.buffer[-structure["footer"]["length"]:]
        )

    def _unpack_arg_values(self, args, known_length, unpack_format, buffer):
        dictionary = perilib_core.dotdict()
        values = struct.unpack(unpack_format, buffer[:known_length])
        for i, arg in enumerate(args):
            if arg["type"] in ["uint8a-l8v", "uint8a-l16v", "uint8a-greedy"]:
                # use the byte array contained in the rest of the payload
                if arg["type"] != "uint8a-greedy" and values[i] + known_length != len(buffer):
                    raise perilib_core.PerilibProtocolException("Specified variable payload length %d does not match actual remaining payload length %d" % (values[i], len(buffer) - known_length))
                dictionary[arg["name"]] = buffer[known_length:]
            elif arg["type"] == "macaddr":
                # special handling for 6-byte MAC address
                dictionary[arg["name"]] = [x for x in values[i]]
            else:
                # use the value extracted during unpacking
                dictionary[arg["name"]] = values[i]
        return dictionary

    def build_buffer_from_structure(self):
        # identify correct set of args based on packet type
        args = self.definition[self.TYPE_ARG_CONTEXT[self.type]]

        # build out pack format string and verify all arguments
        pack_format = "<"
        for arg in args:
            pack_format += StreamProtocol.types[arg["type"]]["pack"]

        # pack all arguments into binary buffer
        self.buffer = b''

        # allow arbitrary buffer manipulation, e.g. adding headers/footers
        # (easier to re-implement just that instead of this whole method)
        self.prepare_buffer_after_building()

    def prepare_buffer_after_building(self):
        return

class ParserGenerator:

    STATUS_IDLE = 0
    STATUS_STARTING = 1
    STATUS_IN_PROGRESS = 2
    STATUS_COMPLETE = 3

    def __init__(self, protocol=StreamProtocol(),
                 on_rx_packet=None, on_packet_timeout=None, on_rx_error=None,
                 test_packet_start=None, test_packet_complete=None,
                 timeout=None):
        self.protocol = protocol
        self.on_rx_packet = on_rx_packet
        self.on_packet_timeout = on_packet_timeout
        self.on_rx_error = on_rx_error
        self.timeout = timeout
        self.timer = None
        self.last_rx_packet = None
        self.reset()

    def reset(self):
        self.rx_buffer = b''
        self.parser_status = ParserGenerator.STATUS_IDLE
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def parse(self, input_data, port_info=None):
        if isinstance(input_data, (int,)):
            # given a single integer, so convert it to bytes first
            input_data = bytes([input_data])
        elif isinstance(input_data, (list,)):
            # given a list, so convert it to bytes first
            input_data = bytes(input_data)

        for input_byte_as_int in input_data:
            if self.parser_status == ParserGenerator.STATUS_IDLE:
                # not already in a packet, so run through start boundary test function
                self.parser_status = self.protocol.test_packet_start(bytes([input_byte_as_int]), port_info)

                # if we just started and there's a defined timeout, start the timer
                if self.parser_status != ParserGenerator.STATUS_IDLE and self.timeout is not None:
                    self.timer = threading.Timer(self.timeout, self._timed_out)
                    self.timer.start()

            # if we are (or may be) in a packet now, process
            if self.parser_status != ParserGenerator.STATUS_IDLE:
                # add byte to the buffer
                self.rx_buffer += bytes([input_byte_as_int])

                # continue testing start conditions if we haven't fully started yet
                if self.parser_status == ParserGenerator.STATUS_STARTING:
                    self.parser_status = self.protocol.test_packet_start(self.rx_buffer, port_info)

                # test for completion conditions if we've fully started
                if self.parser_status == ParserGenerator.STATUS_IN_PROGRESS:
                    self.parser_status = self.protocol.test_packet_complete(self.rx_buffer, port_info)

                # process the complete packet if we finished
                if self.parser_status == ParserGenerator.STATUS_COMPLETE:
                    # convert the buffer to a packet
                    try:
                        self.last_rx_packet = self.protocol.get_packet_from_buffer(self.rx_buffer, port_info)
                        if self.last_rx_packet is not None and self.on_rx_packet:
                            # pass packet to receive callback
                            self.on_rx_packet(self.last_rx_packet)
                    except perilib_core.PerilibProtocolException as e:
                        if self.on_rx_error is not None:
                            self.on_rx_error(e, self.rx_buffer, port_info)

                    # reset the parser
                    self.reset()

    def generate(self, _packet_name, _port_info, **kwargs):
        # args are prefixed with '_' to avoid unlikely collision with kwargs key
        return self.protocol.get_packet_from_name_and_args(_packet_name, _port_info, **kwargs)

    def _timed_out(self):
        if self.on_packet_timeout is not None:
            # pass partial packet to timeout callback
            self.on_packet_timeout(self.rx_buffer)

        # reset the parser
        self.reset()