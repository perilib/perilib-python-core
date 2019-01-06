"""Perilib Core Definitions

These items are made available to all Perilib code. Most functionality is at
least one level down (monitors, hardware, and protocols), so if this seems a bit
sparse, well...that's because it is.
"""

class PerilibException(Exception):
    """Base exception class for any Perilib-related exception
    
    This type may be used to catch Perilib exceptions generally within an
    application, but should not be raised directly. Rather, extend the class
    into something more specific (as in the PerilibProtocolException) and then
    raise that instead.
    """
    
    pass

class PerilibMonitorException(PerilibException):
    """Monitor exception class for device connectivity monitor functions
    
    Currently, Perilib code does not raise this exception, but it is provided
    here as a base class for future expansion.
    """
    
    pass

class PerilibHalException(PerilibException):
    """Protocol exception class for any hardware access functions
    
    Perilib code raises this type of exception if a base class method is not
    correctly re-implemented in a child class (e.g. `Stream.open` vs.
    `SerialStream.open`), or in case of otherwise unrecoverable hardware access
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

class dotdict(dict):
    """Provides `dot.notation` access to dictionary attributes

    This class provides convenience access to dictionary data, specifically
    used on the `header`, `payload`, and `footer` dictionaries that are
    populated after fully parsing a packet. This implementation comes, as so
    so many wonderful things, from StackOverflow:
    
    http://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary
    """
    
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
    
