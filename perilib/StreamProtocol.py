import struct

from .common import *
from .Exceptions import *

class StreamProtocol():
    """Generic stream protocol definition.
    
    This class provides a foundation for stream-based protocols, including stub
    methods required to detect packet boundaries and instantiate new packet
    instances from incoming data. Without subclassing, this considers every new
    byte to be a new packet, which is not suitable for virtually any real use
    case. You will most likely need to implement a subclass with more specific
    boundary detection (at the very least) suitable to the specific protocol
    that is being used.
    
    It also contains attributes and methods capable of describing, packing, and
    unpacking binary data to and from byte buffers. Further detail and
    transport-specific processing are left to subclasses."""

    types = {
        "uint8":                { "pack": "B", "width": 1 },
        "uint16":               { "pack": "H", "width": 2 },
        "uint32":               { "pack": "L", "width": 4 },
        "int8":                 { "pack": "b", "width": 1 },
        "int16":                { "pack": "h", "width": 2 },
        "int32":                { "pack": "l", "width": 4 },
        "float":                { "pack": "f", "width": 4 },
        "macaddr":              { "pack": "6s", "width": 6 },
        "uint8a-l8v":           { "pack": "B", "width": 1 },
        "uint8a-l16v":          { "pack": "H", "width": 2 },
        "uint8a-greedy":        { "pack": "", "width": 0 },
        "uint8a-fixed":         { "pack": "", "width": 0 },
    }

    incoming_packet_timeout = None
    response_packet_timeout = None
    
    backspace_bytes = None
    terminal_bytes = None
    trim_bytes = None

    @classmethod
    def calculate_packing_info(cls, fields):
        """Build a struct.pack format string and calculate expected data length
        based on field definitions.
        
        :param fields: A list containing field definitions describing the
                packing structure
        :type fields: list

        :returns: Dictionary containing packing format and calculated data
                length in bytes
        :rtype: dict
        """
        
        pack_format = "<"
        expected_length = 0

        # build out unpack format string and calculate expected byte count
        for field in fields:
            # use format and length from field type definition
            pack_format += cls.types[field["type"]]["pack"]
            expected_length += cls.types[field["type"]]["width"]
            
            # process types that require special handling
            if field["type"] == "uint8a-fixed":
                # fixed-width uint8a fields specify their own width
                pack_format += "%ds" % field["width"]
                expected_length += field["width"]

        return { "pack_format": pack_format, "expected_length": expected_length }

    @classmethod
    def calculate_field_offset(cls, fields, field_name):
        """Determine the byte offset for a specific field within a packed byte
        buffer.
        
        :param fields: A list containing field definitions describing the
                packing structure
        :type fields: list
        
        :param field_name: Specific field for which to calculate the offset
        :type field_name: str
        
        :returns: Byte offset for supplied field, or None if not found
        :rtype: int
        """
        
        offset = 0
        for field in fields:
            if field["name"] == field_name:
                # found the field, so use the current offset
                return offset
            else:
                # not found yet, so add this width to the running offset
                offset += cls.types[field["type"]]["width"]
                
                # process types that require special handling
                if field["type"] == "uint8a-fixed":
                    # fixed-width uint8a fields specify their own width
                    offset += field["width"]
        
        # not found
        return None

    @classmethod
    def pack_values(cls, values, fields, packing_info=None):
        """Pack a dictionary into a binary buffer based on field definitions.
        
        :param values: A list containing values to be packed according to the
                supplied field definition list
        :type fields: list

        :param fields: A list containing field definitions describing the
                packing structure
        :type fields: list

        :param packing_info: A dictionary containing the packing format string
                and expected length in bytes for the corresponding buffer
        :type packing_info: dict

        :returns: Packet byte buffer packed from dictionary
        :rtype: bytes

        If no packing info is provided as an argument, it will be obtained as
        part of the process. It is allowed to be sent as an argument because
        some external methods require access to it for pre-processing, and so
        it would be a waste to force the calculation twice."""
        
        if packing_info is None:
            packing_info = cls.calculate_packing_info(fields)

        value_list = []
        for field in fields:
            if field["name"] not in values:
                raise PerilibProtocolException("Field '%s' value is required to build packet " % field["name"])
            if field["type"] in ["uint8a-l8v", "uint8a-l16v"]:
                # variable-length blob with 8-bit or 16-bit length prefix
                blob = bytes(values[field["name"]])
                packing_info["pack_format"] += ("%ds" % len(blob))
                value_list.append(len(blob))
                value_list.append(blob)
            elif field["type"] == "uint8a-greedy":
                # greedy byte blob with no specified length prefix, so it's only
                # possible to know/specify the length at packing time
                blob = bytes(values[field["name"]])
                packing_info["pack_format"] += ("%ds" % len(blob))
                value_list.append(blob)
            else:
                # standard argument
                value_list.append(values[field["name"]])

        # pack all arguments into binary buffer
        return struct.pack(packing_info["pack_format"], *value_list)
        
    @classmethod
    def unpack_values(cls, buffer, fields, packing_info=None):
        """Unpack a binary buffer into a dictionary based on field definitions.
        
        :param buffer: A byte buffer to be unpacked into a dictionary based on
                the supplied field definition list
        :type buffer: bytes

        :param fields: A list containing field definitions describing the
                packing structure
        :type fields: list

        :param packing_info: A dictionary containing the packing format string
                and expected length in bytes for the corresponding buffer
        :type packing_info: dict

        :returns: Dictionary unpacked from byte buffer
        :rtype: dict

        If no packing info is provided as an argument, it will be obtained as
        part of the process. It is allowed to be sent as an argument because
        some external methods require access to it for pre-processing, and so
        it would be a waste to force the calculation twice."""

        values = dotdict()
        
        if packing_info is None:
            packing_info = cls.calculate_packing_info(fields)
        
        # make sure calculated lengths are sane
        if packing_info["expected_length"] > len(buffer):
            raise PerilibProtocolException("Calculated minimum buffer length %d exceeds actual buffer length %d" % (packing_info["expected_length"], len(buffer)))

        unpacked = struct.unpack(packing_info["pack_format"], buffer[:packing_info["expected_length"]])
        for i, field in enumerate(fields):
            if field["type"] in ["uint8a-l8v", "uint8a-l16v", "uint8a-greedy"]:
                # use the byte array contained in the rest of the payload
                if field["type"] != "uint8a-greedy" and unpacked[i] + packing_info["expected_length"] != len(buffer):
                    raise PerilibProtocolException(
                        "Specified variable payload length %d does not match actual "
                        "remaining payload length %d"
                        % (values[field["name"]], len(buffer) - packing_info["expected_length"]))
                values[field["name"]] = buffer[packing_info["expected_length"]:]
            elif field["type"] == "macaddr":
                # special handling for 6-byte MAC address
                values[field["name"]] = [x for x in unpacked[i]]
            else:
                # directly use the value extracted during unpacking
                values[field["name"]] = unpacked[i]
        
        # done!
        return values

    @classmethod
    def test_packet_start(cls, buffer, is_tx=False):
        """Test whether a packet has started.
        
        :param buffer: Current data buffer
        :type buffer: bytes

        :param is_tx: Whether the data is incoming (false) or outgoing (true)
        :type is_tx: boolean

        Since many protocols have a unique mechanism for determining the start
        of a new frame (e.g. 0x55 byte), this method may be overridden to use a
        more complex test based on the contents of the `buffer` argument (which
        is a `bytes` object). The default implementation here assumes that any
        data received is the beginning of a new packet.
        
        Available return values are STATUS_IN_PROGRESS to indicate that the
        packet has started, STATUS_STARTING to indicate that additional bytes
        are necessary before knowing for sure that the packet has started, and
        STATUS_IDLE to indicate that no packet has started and the parser should
        return to an idle state.
        
        This class method is called automatically by the parser/generator object
        when new data is received and passed to the parse method."""
        
        return ParseStatus.IN_PROGRESS

    @classmethod
    def test_packet_complete(cls, buffer, is_tx=False):
        """Test whether a packet has finished.
        
        :param buffer: Current data buffer (not including new byte)
        :type buffer: bytes

        :param is_tx: Whether the data is incoming (false) or outgoing (true)
        :type is_tx: boolean

        Almost every protocol has a way to determine when an incoming packet is
        complete, especially if each packet may be a different length. Often,
        packets end with a CRC block or other type of validation data that must
        be checked in order to accept the packet as valid. This method may be
        overridden to check whatever conditions are necessary against on the
        contents of the `buffer` argument (which is a `bytes` object). The
        default implementation here assumes any data is the end of a new packet.
        
        NOTE: in combination with the default start test condition, this means
        that each individual byte received is treated as a complete packet. This
        is ALMOST CERTAINLY not what you want, so one or both of these methods
        should be overridden with specific conditions for real protocols.
        
        Suitable return values are STATUS_IN_PROGRESS to indicate that the
        packet is not yet finished, STATUS_COMPLETE to indicate that the packet
        is complete and valid and should be processed, and STATUS_IDLE to
        indicate that the previously in-progresss packet has failed validation
        of some type and data should be dropped.
        
        This class method is called automatically by the parser/generator object
        when new data is received and passed to the parse method."""
        
        # check for simple byte-based terminal condition
        if cls.terminal_bytes is not None and len(cls.terminal_bytes) > 0:
            # check for a byte match
            for b in cls.terminal_bytes:
                if buffer[-1] == b:
                    # matching terminal byte, packet is complete
                    return ParseStatus.COMPLETE

            # no match, packet is incomplete
            return ParseStatus.IN_PROGRESS

        # no terminal conditions, assume completion after any byte
        return ParseStatus.COMPLETE

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False):
        """Generates a packet object from a binary buffer.
        
        :param buffer: Data buffer from which to create a packet object
        :type buffer: bytes

        :param parser_generator: Parser/generator object to associate with the
                newly created packet, if any
        :type parser_generator: StreamParserGenerator

        :param is_tx: Whether the buffer is incoming (false) or outgoing (true)
                data
        :type is_tx: boolean

        Internally, this method is called once an incoming packet is received
        without error. This method accepts the buffer, parser/generator object,
        and packet direction (RX or TX) and must assembled a fully populated
        packet object using this information. The `is_tx` argument is provided
        in case the direction of data flow is itself an indicator of the type of
        packet, e.g. a command vs. response packet which structurally look the
        same but must be one or the other based on which device sent the packet.
        
        The parser/generator object is also provided in case some specific state
        information maintained by this object is required in order to correctly
        identify the packet.
        
        This method must do the following:
        
        1. Identify the correct packet definition based on the binary content
        2. Unpack all of the binary data into a dictionary
        3. Validate the dictionary contents (argument data) based on the packet
           definition

        This default implementation does not assume anything about the buffer
        content, but simply creates a packet instance directly without any
        special processing. In virtually every real use case, child classes
        *will* need to override this implementation."""
        
        return StreamPacket(buffer=buffer, parser_generator=parser_generator)

    @classmethod
    def get_packet_from_name_and_args(cls, _packet_name, _parser_generator=None, **kwargs):
        """Generates a packet object from a name and argument dictionary.
        
        :param _packet_name: Name of the packet to search for
        :type _packet_name: str

        :param _parser_generator: Parser/generator object to associate with the
                newly created packet, if any
        :type _parser_generator: StreamParserGenerator

        :param kwargs: Dictionray of arguments to use for assembling the packet
        :type kwargs: dict

        Internally, this method is called in order to create a packet and fill
        the binary buffer prior to transmission, typically as a result of a call
        to the `send_packet()` or `send_and_wait()` method. The `kwargs`
        dictionary contains the named packet arguments which must be converted
        into a packed binary structure (if any are required).
        
        This method must do the following:
        
        1. Identify the correct packet definition based on the supplied name
        2. Validate the supplied arguments based on the packet definition
        3. Pack all of the arguments into a binary buffer (`bytes()` object)
        
        Child classes must override this method since this process requires a
        custom protocol definition to work with, e.g. a list containing packet
        structures and argument names/types for each packet, and this is not
        available in the base class."""
        
        raise PerilibProtocolException(
                "Cannot generate '%s' packet using base StreamProtocol method, "
                "no definitions available", _packet_name)
