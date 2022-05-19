from .StreamProtocol import *

class StreamPacket():
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
        """Creates a new stream packet instance.

        :param type: Packet type
        :type type: int

        :param name: Name of the packet
        :type name: str

        :param definition: Structure of this packet from the protocol definition
        :type definition: dict

        :param buffer: Binary buffer from which to create the packet
        :type buffer: bytes

        :param header: Header arguments for this packet, if any
        :type header: dict

        :param payload: Payload arguments for this packet, if any
        :type payload: dict

        :param footer: Footer arguments for this packet, if any
        :type footer: dict

        :param metadata: Custom metadata for this packet, if any
        :type metadata: dict

        :param parser_generator: Parser/generator object to associate with the
                newly created packet, if any
        :type parser_generator: StreamParserGenerator

        Supplying particular combinations of arguments to this constructor will
        result in a fully populated/configured packet instance. Most often, this
        is used to create a new packet object either from a binary buffer (which
        is mapped to a packet name and argument dictionary for processing) or
        from a packet name and argument dictionary (which is converted into a
        binary buffer ready for transmission).

        In both of these cases, the structural definition of the packet must be
        supplied as well, or no conversion can occur. It is assumed that the
        caller will already have identified the right entry in the relevant
        protocol class, and will then pass this along (with any required packet-
        specific modifications) in the `definition` argument.
        """

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
        """Convenience accessor for payload arguments.

        :param arg: Name of the payload argument to get
        :type arg: str

        With this method, you can directly read payload entries without
        explicitly using the `.payload` attribute, but rather using the packet
        object itself as a dictionary."""

        return self.payload[arg]

    def __str__(self):
        """Generates the string representation of the device.

        This implementation displays the packet name, type, payload details, and
        stream source (if available). It provides a good foundation for quick
        console displays or debugging information. Raw binary structure is not
        shown."""

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

    def build_structure_from_buffer(self) -> None:
        """Fills packet structure data based on a byte buffer and definition.

        This method uses the already-stored packet definition and binary byte
        buffer to unpack the contents into a dictionary, including (where
        necessary) header and footer information. The definition and byte
        buffer must already have been supplied before calling this method. The
        class constructor automatically calls this method if both a definition
        and byte buffer are supplied when instantiating a new packet, but you
        can also call it by hand afterwards if necessary."""

        # header (optional)
        if "header_args" in self.definition:
            header_packing_info = StreamProtocol.calculate_packing_info(self.definition["header_args"])
            header_expected_length = header_packing_info["expected_length"]
            self.header = StreamProtocol.unpack_values(
                self.buffer[:header_expected_length],
                self.definition["header_args"],
                header_packing_info
            )
        else:
            self.header = {}
            header_expected_length = 0

        # footer (optional)
        if "footer_args" in self.definition:
            footer_packing_info = StreamProtocol.calculate_packing_info(self.definition["footer_args"])
            footer_expected_length = footer_packing_info["expected_length"]
            self.footer = StreamProtocol.unpack_values(
                    self.buffer[-footer_expected_length:],
                    self.definition["footer_args"],
                    footer_packing_info)
        else:
            self.footer = {}
            footer_expected_length = 0

        # payload (required)
        payload_packing_info = StreamProtocol.calculate_packing_info(self.definition[self.TYPE_ARG_CONTEXT[self.type]])
        self.payload = StreamProtocol.unpack_values(
                self.buffer[header_expected_length:len(self.buffer)-footer_expected_length],
                self.definition[self.TYPE_ARG_CONTEXT[self.type]],
                payload_packing_info)

    def build_buffer_from_structure(self) -> None:
        """Generates a binary buffer based on a dictionary and definition.

        This method uses the already-stored packet definition and argument
        dictionary to create a byte buffer representing the payload of a packet,
        ready for transmission using a stream object. Note that many protocols
        will need to add further content before and/or after the payload, using
        headers and footers. Since this is optional and usually dependent on
        protocol-specific metadata and/or payload content (such as CRC
        calculation), the post-creation method is separated from this one to
        simplify overriding only that part. Normally, you will not need to
        override this particular method in a subclass."""

        # pack all arguments into binary buffer
        payload_packing_info = StreamProtocol.calculate_packing_info(self.definition[self.TYPE_ARG_CONTEXT[self.type]])
        self.buffer = StreamProtocol.pack_values(
                self.payload,
                self.definition[self.TYPE_ARG_CONTEXT[self.type]],
                payload_packing_info)

        # allow arbitrary buffer manipulation, e.g. adding headers/footers
        # (easier to re-implement just that instead of this whole method)
        self.prepare_buffer_after_building()

    def prepare_buffer_after_building(self) -> None:
        """Perform final modifications to buffer after packing the payload.

        Protocols that require a header (e.g. type/length data) and/or footer
        (e.g. CRC data) can override this method to prepend/append or otherwise
        modify data in the packet buffer before the dictionary-to-byte-array
        conversion process is considered to be complete. The stub implementation
        in this base class simply does nothing."""

        pass
