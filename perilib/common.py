class ProcessMode:
    SELF = 1
    SUBS = 2
    BOTH = 3

class ParseStatus:
    IDLE = 0
    STARTING = 1
    IN_PROGRESS = 2
    COMPLETE = 3

class Order:
    LITTLE_ENDIAN = 0
    BIG_ENDIAN = 1

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
