from .common import *
from .StreamProtocol import *
from .StreamPacket import *

class TLVStreamProtocol(StreamProtocol):

    @classmethod
    def test_packet_complete(cls, buffer, is_tx=False) -> ParseStatus:
        # simple terminal condition for TLV data, where T/L are single bytes
        # [type] [length] [v0, v1, ..., v<length>]
        if len(buffer) > 1 and len(buffer) == buffer[1] + 2:
            return ParseStatus.COMPLETE
        else:
            return ParseStatus.IN_PROGRESS

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False) -> StreamPacket:
        definition = {
            "name": "tlv_packet",
            "args": [
                { "name": "type", "type": "uint8" },
                { "name": "length", "type": "uint8" },
                { "name": "value", "type": "uint8a-greedy" }
            ]
        }
        return StreamPacket(buffer=buffer, definition=definition, parser_generator=parser_generator)
