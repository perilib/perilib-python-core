import perilib

class LTVProtocol(perilib.protocol.stream.core.StreamProtocol):

    def test_packet_complete(self, buffer, is_tx=False):
        # simple terminal condition for LTV data, where L/T are single bytes
        # [length] [type] [v0, v1, ..., v<length>]
        if len(buffer) > 0 and len(buffer) == buffer[0] + 1:
            return perilib.protocol.stream.core.ParserGenerator.STATUS_COMPLETE
        else:
            return perilib.protocol.stream.core.ParserGenerator.STATUS_IN_PROGRESS

    def get_packet_from_buffer(self, buffer, port_info=None, is_tx=False):
        definition = {
            "name": "ltv_packet",
            "args": [
                { "name": "length", "type": "uint8" },
                { "name": "type", "type": "uint8" },
                { "name": "value", "type": "uint8a-greedy" }
            ]
        }
        return LTVPacket(buffer=buffer, definition=definition, port_info=port_info)

class LTVPacket(perilib.protocol.stream.core.StreamPacket):

    pass
