from .common import *

class Stream:
    """Base stream class to manage bidirectional data streams.
    
    This class represents a data stream and is optionally associated with a
    device and/or a parser/generator object to manage connectivity monitoring
    and protocol decoding/encoding. However, it is fundamentally separate from
    these higher and lower layers in the communication stack, and internally
    manages only receiption and transmission of data. It spawns a dedicated
    thread to monitor for incoming data, allowing the main application thread
    to continue executing without blocking.
    
    This class should not be used directly, but rather used as a base for child
    classes that use specific low-level communication drivers. As a minimum, a
    child class must implement the `open()`, `close()`, `write()`, and
    `_watch_data()` methods."""

    def __init__(self, device=None, parser_generator=None):
        """Initializes a stream instance.
        
        :param device: Device which manages this stream, if one exists
        :type device: Device
        
        :param parser_generator: Parser/generator object which this stream
            sends and receives data through, if one exists
        :type parser_generator: ParserGenerator

        A device (which has a stream) and parser/generator (which a stream has)
        may be supplied at instantiation, or later if required. A stream does
        not strictly need either of these things, but in most cases you will be
        using both, so it makes sense to provide them for reference later."""

        # these attributes may be updated by the application
        self.device = device
        self.parser_generator = parser_generator
        self.use_threading = False
        self.on_open_stream = None
        self.on_close_stream = None
        self.on_rx_data = None
        self.on_tx_data = None
        self.on_disconnect_device = None
        
        # these attributes should only be read externally, not written
        self.is_running = False
        self.is_open = False

        # these attributes are intended to be private
        self._port_open = False
        self._running_thread_ident = 0
        self._stop_thread_ident_list = []

    def __str__(self):
        """Generates the string representation of the stream.
        
        :returns: String representation of the device
        :rtype: str

        This basic implementation simply uses the string representation of the
        assigned device. If no device is supplied, this will of course return
        the string "None" instead."""
        
        return str(self.device)

    def open(self):
        """Opens the stream.
        
        For example, a stream using PySerial as the underlying driver would use
        the `open()` method on the serial port object whenever this method is
        called.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Opening a
        stream driven by nothing at all will generate an exception."""
        
        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented open() method, cannot use base class stub")

    def close(self):
        """Closes the stream.
        
        For example, a stream using PySerial as the underlying driver would use
        the `close()` method on the serial port object whenever this method is
        called.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Closing a
        stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented close() method, cannot use base class stub")

    def write(self, data):
        """Sends outgoing data to the stream.
        
        :param data: Data buffer to be sent out to the stream
        :type data: bytes

        For example, a stream using PySerial as the underlying driver would use
        the `write()` method on the serial port object whenever this method is
        called.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Writing data
        to a stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented write() method, cannot use base class stub")

    def start(self):
        """Starts monitoring for incoming data.
        
        If you have not previously configured this object to use threading,
        calling this method will enable it. If you do not want to use threading
        in your app, you should periodically call the `process()` method in a
        loop instead (either directly on the stream, or in the parent manager
        object, if one exists)."""

        # don't start if we're already running
        if not self.is_running:
            self._monitor_thread = threading.Thread(target=self._watch_data)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            self._running_thread_ident = self._monitor_thread.ident
            self.use_threading = True
            self.is_running = True

    def stop(self):
        """Stops monitoring for incoming data.
        
        If the stream was previously monitoring incoming data, this method will
        stop it. This method is automatically called if the port is closed, but
        you can also call it directly without closing the port if you wish to
        switch to non-threaded or otherwise manual data monitoring."""
        
        # don't stop if we're not running
        if self.is_running:
            self._stop_thread_ident_list.append(self._running_thread_ident)
            self._running_thread_ident = 0
            self.is_running = False
            
    def process(self, mode=ProcessMode.BOTH, force=False):
        """Handle any pending events or data waiting to be processed.
        
        :param mode: Processing mode defining whether to run for this object,
            sub-objects lower in the management hierarchy (parser/generator
            objects in this case), or both
        :type mode: int
        
        :param force: Whether to force processing to run regardless of elapsed
            time since last time (if applicable)
        :type force: bool
            
        If the stream is being used in a non-threading arrangement, this method
        should periodically be executed to manually step through all necessary
        checks and trigger any relevant data processing and callbacks. Calling
        this method will automatically call it on an associated parser/generator
        object.
        
        This is the same method that would be called internally in an infinite
        loop by the thread target, if threading is used.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Processing a
        stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented process() method, cannot use base class stub")

    def _watch_data(self):
        """Watches the stream for incoming data.
        
        For example, a stream using PySerial as the underlying driver would use
        the `read()` method on the serial port object whenever this method is
        called.
        
        Note that this method is not intended for application use; rather, it is
        executed in a separate thread after the stream is opened in order to
        allow a non-blocking mechanism for efficient RX monitoring. If any data
        is received, this method will pass it to the `_on_rx_data()` method
        to be optionally processed and/or handed to the application-exposed
        `on_rx_data()` callback.
        
        Overridden implementations of this method should run in an infinite loop
        and safely handle any exceptions that might occur, so that the RX data
        monitoring thread will not terminate unexpectedly.
        
        Since no driver is inherent in the base class, you *must* override this
        method in child classes so that a suitable action occurs. Watching data
        on a stream driven by nothing at all will generate an exception."""

        # child class must implement
        raise perilib_core.PerilibHalException("Child class has not implemented _watch_data() method, cannot use base class stub")

    def _on_rx_data(self, data):
        """Handles incoming data.
        
        :param data: Data buffer that has just been received
        :type data: bytes

        When the data watcher method receives any data (one or more bytes), that
        chunk is passed to this method for processing. This simple default
        implementation merely passes it directly to the application-level data
        RX callback, if one is defined, with no additional buffering or
        processing.
        
        Child classes *may* override this implementation, but often this will
        not be necessary unless the stream itself needs extra insight into the
        data content."""

        # child class may re-implement
        run_builtin = True
        if self.on_rx_data:
            run_builtin = self.on_rx_data(data, self)
            
        # derived Stream classes can do special things at this point
        #if run_builtin != False:
            # do fun stuff automatically
