import perilib

class TLVStreamProtocol(perilib.StreamProtocol):

    @classmethod
    def test_packet_complete(cls, buffer, new_byte, is_tx=False):
        # simple terminal condition for TLV data, where T/L are single bytes
        # [type] [length] [v0, v1, ..., v<length>]
        if len(buffer) > 1 and len(buffer) + 1 == buffer[1] + 2:
            return perilib.ParseStatus.COMPLETE
        else:
            return perilib.ParseStatus.IN_PROGRESS

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
        return perilib.StreamPacket(buffer=buffer, definition=definition, parser_generator=parser_generator)
