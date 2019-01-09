import perilib

class LTVProtocol(perilib.protocol.stream.core.StreamProtocol):

    @classmethod
    def test_packet_complete(cls, buffer, is_tx=False):
        # simple terminal condition for LTV data, where L/T are single bytes
        # [length] [type] [v0, v1, ..., v<length>]
        if len(buffer) > 0 and len(buffer) == buffer[0] + 1:
            return perilib.protocol.stream.core.StreamParserGenerator.STATUS_COMPLETE
        else:
            return perilib.protocol.stream.core.StreamParserGenerator.STATUS_IN_PROGRESS

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False):
        definition = {
            "name": "ltv_packet",
            "args": [
                { "name": "length", "type": "uint8" },
                { "name": "type", "type": "uint8" },
                { "name": "value", "type": "uint8a-greedy" }
            ]
        }
        return LTVPacket(buffer=buffer, definition=definition, parser_generator=parser_generator)

class LTVPacket(perilib.protocol.stream.core.StreamPacket):

    pass
