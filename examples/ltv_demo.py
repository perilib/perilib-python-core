import time

try:
    # standard library installation
    import perilib
    print("Detected standard perilib-python installation")
except ImportError as e:
    # local development installation
    import sys
    sys.path.insert(0, "../../../..") # submodule upwards to perilib root
    sys.path.insert(0, ".") # submodule root
    try:
        import perilib
        print("Detected development perilib-python installation run from submodule root")
    except ImportError as e:
        sys.path.insert(0, "../../../../..") # submodule/examples upwards to perilib root
        sys.path.insert(0, "..") # submodule/examples upwards to submodule root
        try:
            import perilib
            print("Detected development perilib-python installation run from submodule/example folder")
        except ImportError as e:
            print("Unable to find perilib-python installation, cannot continue")
            sys.exit(1)

from perilib.protocol.stream.generic import LTVProtocol

class App():

    def __init__(self):
        # set up protocol parser (handles imcoming data and builds outgoing data)
        self.parser_generator = perilib.protocol.stream.core.ParserGenerator(protocol=LTVProtocol())
        self.parser_generator.on_rx_packet = self.on_rx_packet
        self.parser_generator.on_rx_error = self.on_rx_error

    def on_rx_packet(self, packet):
        print("[%.03f] RX: [%s] (%s)" % (time.time(), ' '.join(["%02X" % b for b in packet.buffer]), packet))

    def on_rx_error(self, e, rx_buffer, port_info):
        print("[%.03f] ERROR: %s (raw data: [%s] from %s)" % (time.time(), e, ' '.join(["%02X" % b for b in rx_buffer]), port_info.name if port_info is not None else "unidentified port"))

def main():
    app = App()
    [app.parser_generator.parse(x) for x in [0x06, 0x01, 0x48, 0x65, 0x6C, 0x6C, 0x6F]]
    [app.parser_generator.parse(x) for x in [0x06, 0x02, 0x77, 0x6F, 0x72, 0x6C, 0x64]]
    [app.parser_generator.parse(x) for x in [0x04, 0x03, 0x4C, 0x54, 0x56]]
    [app.parser_generator.parse(x) for x in [0x05, 0x04, 0x64, 0x65, 0x6D, 0x6F]]

if __name__ == '__main__':
    main()
