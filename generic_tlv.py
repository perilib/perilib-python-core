import perilib

class TLVProtocol(perilib.protocol.stream.core.StreamProtocol):

    def test_packet_complete(self, buffer, is_tx=False):
        # simple terminal condition for TLV data, where T/L are single bytes
        # [type] [length] [v0, v1, ..., v<length>]
        if len(buffer) > 1 and len(buffer) == buffer[1] + 2:
            return perilib.protocol.stream.core.ParserGenerator.STATUS_COMPLETE
        else:
            return perilib.protocol.stream.core.ParserGenerator.STATUS_IN_PROGRESS

    def get_packet_from_buffer(self, buffer, port_info=None, is_tx=False):
        definition = {
            "name": "tlv_packet",
            "args": [
                { "name": "type", "type": "uint8" },
                { "name": "length", "type": "uint8" },
                { "name": "value", "type": "uint8a-greedy" }
            ]
        }
        return TLVPacket(buffer=buffer, definition=definition, port_info=port_info)

class TLVPacket(perilib.protocol.stream.core.StreamPacket):

    pass
