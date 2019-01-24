"""
This module provides protocol, packet, and parser/generator implementations for
generic stream-based communication. Some protocols and devices will be able to
use much of this code as-is, although at least the protocol definition will need
to be subclassed to provide boundary and vocabulary definitions. Other protocols
and devices may need to customize significant chunks of the implementation.
"""

# .py files
from .core import *
