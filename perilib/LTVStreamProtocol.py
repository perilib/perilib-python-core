from .common import *
from .StreamProtocol import *
from .StreamPacket import *

class LTVStreamProtocol(StreamProtocol):

    @classmethod
    def test_packet_complete(cls, buffer, is_tx=False) -> ParseStatus:
        # simple terminal condition for LTV data, where L/T are single bytes
        # [length] [type] [v0, v1, ..., v<length-1>]
        if len(buffer) == buffer[0] + 1:
            return ParseStatus.COMPLETE
        else:
            return ParseStatus.IN_PROGRESS

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False) -> StreamPacket:
        definition = {
            "name": "ltv_packet",
            "args": [
                { "name": "length", "type": "uint8" },
                { "name": "type", "type": "uint8" },
                { "name": "value", "type": "uint8a-greedy" }
            ]
        }
        return StreamPacket(buffer=buffer, definition=definition, parser_generator=parser_generator)
