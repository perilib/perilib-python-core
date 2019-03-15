# check for local development repo in script path and use it for imports
import os, sys
path_parts = os.path.dirname(os.path.realpath(__file__)).split(os.sep)
if "perilib-python-core" in path_parts:
    sys.path.insert(0, os.sep.join(path_parts[:-path_parts[::-1].index("perilib-python-core")]))

import time
import perilib
import perilib.protocol.stream.generic

class App():

    def __init__(self):
        # set up protocol parser (handles incoming data and builds outgoing data)
        self.parser_generator = perilib.protocol.stream.StreamParserGenerator(protocol_class=perilib.protocol.stream.generic.TextProtocol)
        self.parser_generator.on_rx_packet = self.on_rx_packet
        self.parser_generator.on_rx_error = self.on_rx_error

    def on_rx_packet(self, packet):
        print("[%.03f] RXP: %s" % (time.time(), packet))

    def on_rx_error(self, e, rx_buffer, parser_generator):
        print("[%.03f] ERROR: %s (raw data: [%s] via %s)" % (time.time(), e, ' '.join(["%02X" % b for b in rx_buffer]), parser_generator))

def main():
    app = App()

    # parse() call technique 1: actual bytes() object
    app.parser_generator.parse(b"TEST COMMAND 1\r\n")
    app.parser_generator.parse(b"TEST ERR\x08\x08\x08COMMAND 2\r\n")
    
    # parse() call technique 2: list of integers
    app.parser_generator.parse([0x54, 0x45, 0x53, 0x54, 0x20, 0x33, 0x0d, 0x0a])
    
    # parse() call technique 3: single integers
    [app.parser_generator.parse(x) for x in [0x54, 0x45, 0x53, 0x54, 0x20, 0x34, 0x0d, 0x0a]]
    [app.parser_generator.parse(x) for x in [0x54, 0x45, 0x53, 0x54, 0x20, 0x35, 0x0d, 0x0a]]

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Ctrl+C detected, terminating script")
        sys.exit(0)
