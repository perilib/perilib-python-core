import perilib

class TextLineProtocol(perilib.protocol.stream.StreamProtocol):

    @classmethod
    def test_packet_complete(cls, buffer, is_tx=False):
        # simple terminal condition for text data ('\n' or 0x0A byte)
        if buffer[-1] == 0x0A:
            return perilib.protocol.stream.StreamParserGenerator.STATUS_COMPLETE
        else:
            return perilib.protocol.stream.StreamParserGenerator.STATUS_IN_PROGRESS

    @classmethod
    def get_packet_from_buffer(cls, buffer, parser_generator=None, is_tx=False):
        definition = {
            "name": "textline_packet",
            "args": [
                { "name": "text", "type": "uint8a-greedy" }
            ]
        }

        # trim '\n', if it exists
        if buffer[-1] == 0x0A:
            buffer = buffer[:-1]
        # trim '\r', if it exists
        if buffer[-1] == 0x0D:
            buffer = buffer[:-1]
            
        return TextLinePacket(buffer=buffer, definition=definition, parser_generator=parser_generator)

class TextLinePacket(perilib.protocol.stream.StreamPacket):

    pass
