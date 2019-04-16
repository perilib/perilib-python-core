"""
PeriLib is a collection of cross-platform peripheral communication libraries,
including hardware abstraction layers, protocol definitions, data stream parsers
and generators, and related tools.

The perilib-python package is an implementation of these things in Python. It is
split at the top level into monitoring classes, hardware abstraction layer (HAL)
classes, and protocol classes. Protocol classes are further subdivided by type
(currently streaming vs. register-based). See the submodule documentation for
additional detail.

Note that the current perilib-python implementation requires Python 3.x, and
will not work in 2.x.
"""

# .py files
from .common import *
from .Exceptions import *

from .Manager import *
from .Device import *
from .Stream import *

from .StreamDevice import *
from .StreamParserGenerator import *
from .StreamProtocol import *
from .StreamPacket import *

from .TLVStreamProtocol import *
from .LTVStreamProtocol import *
from .TextStreamProtocol import *

# submodule folders
from . import hal
