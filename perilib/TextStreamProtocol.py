from .common import *
from .StreamProtocol import *
from .StreamPacket import *

class TextStreamProtocol(StreamProtocol):

    backspace_bytes = [0x08, 0x7F]
    terminal_bytes = [0x0A]
    trim_bytes = [0x0A, 0x0D]

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False) -> StreamPacket:
        definition = {
            "name": "text_packet",
            "args": [
                { "name": "text", "type": "uint8a-greedy" }
            ]
        }
        return StreamPacket(buffer=buffer, definition=definition, parser_generator=parser_generator)
