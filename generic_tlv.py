import perilib

class TLVProtocol(perilib.protocol.stream.StreamProtocol):

    @classmethod
    def test_packet_complete(cls, buffer, is_tx=False):
        # simple terminal condition for TLV data, where T/L are single bytes
        # [type] [length] [v0, v1, ..., v<length>]
        if len(buffer) > 1 and len(buffer) == buffer[1] + 2:
            return perilib.protocol.stream.StreamParserGenerator.STATUS_COMPLETE
        else:
            return perilib.protocol.stream.StreamParserGenerator.STATUS_IN_PROGRESS

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False):
        definition = {
            "name": "tlv_packet",
            "args": [
                { "name": "type", "type": "uint8" },
                { "name": "length", "type": "uint8" },
                { "name": "value", "type": "uint8a-greedy" }
            ]
        }
        return TLVPacket(buffer=buffer, definition=definition, parser_generator=parser_generator)

class TLVPacket(perilib.protocol.stream.StreamPacket):

    pass
