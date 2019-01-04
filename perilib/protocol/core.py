class Protocol():

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
    }

class Packet():

    pass
