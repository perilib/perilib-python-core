"""
This module provides the lowest-level framework for defining protocols and
packets, including data type definitions that all protocols inherit.

Submodules include extended classes for streaming protocols such as what you
typically need for devices that communicate over UART or USB CDC (virtual
serial).

TODO: Support for register-based protocols used by many I2C slaves
"""

# .py files
from . import core
from . import serial
