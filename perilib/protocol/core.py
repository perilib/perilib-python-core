import struct

from .. import core as perilib_core

class Protocol():
    """Base class underpinning both stream-based and register-based protocols.
    
    This contains class attributes and methods capable of describing, packing,
    and unpacking binary data to and from byte buffers. Further detail and
    transport-specific processing are left to subclasses."""

    types = {
        "uint8":                { "pack": "B", "width": 1 },
        "uint16":               { "pack": "H", "width": 2 },
        "uint32":               { "pack": "L", "width": 4 },
        "int8":                 { "pack": "b", "width": 1 },
        "int16":                { "pack": "h", "width": 2 },
        "int32":                { "pack": "l", "width": 4 },
        "float":                { "pack": "f", "width": 4 },
        "macaddr":              { "pack": "6s", "width": 6 },
        "uint8a-l8v":           { "pack": "B", "width": 1 },
        "uint8a-l16v":          { "pack": "H", "width": 2 },
        "uint8a-greedy":        { "pack": "", "width": 0 },
        "uint8a-fixed":         { "pack": "", "width": 0 },
    }
    
    @classmethod
    def calculate_packing_info(cls, fields):
        """Build a struct.pack format string and calculate expected data length
        based on field definitions."""
        
        pack_format = "<"
        expected_length = 0

        # build out unpack format string and calculate expected byte count
        for field in fields:
            # use format and length from field type definition
            pack_format += Protocol.types[field["type"]]["pack"]
            expected_length += Protocol.types[field["type"]]["width"]
            
            # process types that require special handling
            if field["type"] == "uint8a-fixed":
                # fixed-width uint8a fields specify their own width
                pack_format += "%ds" % field["width"]
                expected_length += field["width"]

        return { "pack_format": pack_format, "expected_length": expected_length }

    @classmethod
    def calculate_field_offset(cls, fields, field_name):
        """Determine the byte offset for a specific field within a packed byte
        buffer."""
        
        offset = 0
        for field in fields:
            if field["name"] == field_name:
                # found the field, so use the current offset
                return offset
            else:
                # not found yet, so add this width to the running offset
                offset += Protocol.types[field["type"]]["width"]
                
                # process types that require special handling
                if field["type"] == "uint8a-fixed":
                    # fixed-width uint8a fields specify their own width
                    offset += field["width"]
        
        # not found
        return None

    @classmethod
    def pack_values(cls, values, fields, packing_info=None):
        """Pack a dictionary into a binary buffer based on field definitions.
        
        If no packing info is provided as an argument, it will be obtained as
        part of the process. It is allowed to be sent as an argument because
        some external methods require access to it for pre-processing, and so
        it would be a waste to force the calculation twice."""
        
        if packing_info is None:
            packing_info = Protocol.calculate_packing_info(fields)

        value_list = []
        for field in fields:
            if field["type"] == "uint8a-greedy":
                # greedy byte blob with no specified length prefix, so it's only
                # possible to know/specify the length at packing time
                blob = bytes(values[field["name"]])
                packing_info["pack_format"] += ("%ds" % len(blob))
                value_list.append(blob)
            else:
                # standard argument
                value_list.append(values[field["name"]])

        # pack all arguments into binary buffer
        return struct.pack(packing_info["pack_format"], *value_list)
        
    @classmethod
    def unpack_values(cls, buffer, fields, packing_info=None):
        """Unpack a binary buffer into a dictionary based on field definitions.
        
        If no packing info is provided as an argument, it will be obtained as
        part of the process. It is allowed to be sent as an argument because
        some external methods require access to it for pre-processing, and so
        it would be a waste to force the calculation twice."""

        values = perilib_core.dotdict()
        
        if packing_info is None:
            packing_info = Protocol.calculate_packing_info(fields)
        
        # make sure calculated lengths are sane
        if packing_info["expected_length"] > len(buffer):
            raise perilib_core.PerilibProtocolException("Calculated minimum buffer length %d exceeds actual buffer length %d" % (expected_length, len(buffer)))

        unpacked = struct.unpack(packing_info["pack_format"], buffer[:packing_info["expected_length"]])
        for i, field in enumerate(fields):
            if field["type"] in ["uint8a-l8v", "uint8a-l16v", "uint8a-greedy"]:
                # use the byte array contained in the rest of the payload
                if field["type"] != "uint8a-greedy" and unpacked[i] + packing_info["expected_length"] != len(buffer):
                    raise perilib_core.PerilibProtocolException(
                        "Specified variable payload length %d does not match actual "
                        "remaining payload length %d"
                        % (values[i], len(buffer) - packing_info["expected_length"]))
                values[field["name"]] = buffer[packing_info["expected_length"]:]
            elif field["type"] == "macaddr":
                # special handling for 6-byte MAC address
                values[field["name"]] = [x for x in unpacked[i]]
            else:
                # directly use the value extracted during unpacking
                values[field["name"]] = unpacked[i]
        
        # done!
        return values

class Packet():
    """Base class underpinning both stream-based and register-based packets.
    
    Currently, this is just a filler class for inheritence purposes. All detail
    and transport-specific processing are left to subclasses."""

    pass
