"""Perilib Exception Definitions

These derived exception classes provide a way for Perilib code to raise unique
exceptions to be caught (optionally) by application code.
"""

class PerilibException(Exception):
    """Base exception class for any Perilib-related exception
    
    This type may be used to catch Perilib exceptions generally within an
    application, but should not be raised directly. Rather, extend the class
    into something more specific (as in the PerilibProtocolException) and then
    raise that instead.
    """
    
    pass

class PerilibHalException(PerilibException):
    """Protocol exception class for any hardware access functions
    
    Perilib code raises this type of exception if a base class method is not
    correctly re-implemented in a child class (e.g. `Stream.open` vs.
    `UartStream.open`), or in case of otherwise unrecoverable hardware access
    errors that bubble up from whatever interface is being used (e.g. trying
    to open a serial port when another process already has the port open).
    """
    
    pass

class PerilibProtocolException(PerilibException):
    """Protocol exception class for parser/generator functions
    
    Perilib code raises this type of exception for cases such as requests for
    protocol entities that don't exist in the definition or malformed packet
    data.
    """
    
    pass
