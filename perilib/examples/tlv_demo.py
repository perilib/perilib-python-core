# check for local development repo in script path and use it for imports
import os, sys
path_parts = os.path.dirname(os.path.realpath(__file__)).split(os.sep)
if "perilib-python-core" in path_parts:
    sys.path.insert(0, os.sep.join(path_parts[:-path_parts[::-1].index("perilib-python-core")]))

import time
import perilib

class App():

    def __init__(self):
        # set up protocol parser (handles imcoming data and builds outgoing data)
        self.parser_generator = perilib.StreamParserGenerator(protocol_class=perilib.TLVStreamProtocol)
        self.parser_generator.on_rx_packet = self.on_rx_packet
        self.parser_generator.on_rx_error = self.on_rx_error

    def on_rx_packet(self, packet):
        print("[%.03f] RXP: %s" % (time.time(), packet))

    def on_rx_error(self, e, rx_buffer, parser_generator):
        print("[%.03f] ERROR: %s (raw data: [%s] via %s)" % (time.time(), e, ' '.join(["%02X" % b for b in rx_buffer]), parser_generator))

def main():
    app = App()

    # parse() call technique 1: actual bytes() object
    app.parser_generator.parse(b"\x01\x05Hello")

    # parse() call technique 2: list of integers
    app.parser_generator.parse([0x02, 0x05, 0x77, 0x6F, 0x72, 0x6C, 0x64])

    # parse() call technique 3: single integers
    [app.parser_generator.parse(x) for x in [0x03, 0x03, 0x54, 0x4C, 0x56]]
    [app.parser_generator.parse(x) for x in [0x04, 0x04, 0x64, 0x65, 0x6D, 0x6F]]

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Ctrl+C detected, terminating script")
        sys.exit(0)
