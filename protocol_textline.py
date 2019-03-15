import perilib

class TextLineProtocol(perilib.protocol.stream.StreamProtocol):
    
    backspace_bytes = [0x08, 0x7F]
    terminal_bytes = [0x0A]
    trim_bytes = [0x0A, 0x0D]

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False):
        definition = {
            "name": "textline_packet",
            "args": [
                { "name": "text", "type": "uint8a-greedy" }
            ]
        }
        
        return TextLinePacket(buffer=buffer, definition=definition, parser_generator=parser_generator)

class TextLinePacket(perilib.protocol.stream.StreamPacket):

    pass
