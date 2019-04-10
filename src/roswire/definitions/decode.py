# -*- coding: utf-8 -*-
"""
This module provides code for decoding and deserialising binary ROS messages
into Python data structures.
"""
from typing import Optional, Iterator, Callable, Any
from io import BytesIO
import struct

_SIMPLE_TO_STRUCT = {
    'int8': 'b',
    'uint8': 'B',
    'bool': 'B',
    'int16': 'h',
    'uint16': 'H',
    'int32': 'i',
    'uint32': 'I',
    'int64': 'q',
    'uint64': 'Q',
    'float32': 'f',
    'float64': 'd',
    # deprecated types
    'char': 'B',  # unsigned
    'byte': 'b'  # signed
}


def is_simple(typ: str) -> bool:
    """Determines whether a given type is a simple type."""
    return typ in _SIMPLE_TO_STRUCT


def get_pattern(typ: str) -> str:
    """Returns the struct pattern for a given simple type."""
    return _SIMPLE_TO_STRUCT[typ]


def simple_decoder(typ: str) -> Callable[[bytes], Any]:
    """Returns a decoder for a specified simple type."""
    pattern = '<' + get_pattern(typ)

    def decoder(v: bytes) -> Any:
        return struct.unpack(pattern, v)[0]

    def bool_decoder(v: bytes) -> bool:
        return bool(struct.unpack(pattern, v)[0])

    return bool_decoder if typ == 'bool' else decoder


def simple_reader(typ: str) -> Callable[[BytesIO], Any]:
    """Returns a reader for a specified simple type."""
    pattern = '<' + get_pattern(typ)
    decoder = simple_decoder(typ)
    size = struct.calcsize(pattern)

    def reader(b: BytesIO) -> Any:
        return decoder(b.read(size))

    return reader


decode_int8 = simple_decoder('int8')
decode_uint8 = simple_decoder('uint8')
decode_int16 = simple_decoder('int16')
decode_uint16 = simple_decoder('uint16')
decode_int32 = simple_decoder('int32')
decode_uint32 = simple_decoder('uint32')
decode_int64 = simple_decoder('int64')
decode_uint64 = simple_decoder('uint64')
decode_float32 = simple_decoder('float32')
decode_float64 = simple_decoder('float64')
decode_char = simple_decoder('char')
decode_byte = simple_decoder('byte')
decode_bool = simple_decoder('bool')

read_int8 = simple_reader('int8')
read_uint8 = simple_reader('uint8')
read_int16 = simple_reader('int16')
read_uint16 = simple_reader('uint16')
read_int32 = simple_reader('int32')
read_uint32 = simple_reader('uint32')
read_int64 = simple_reader('int64')
read_uint64 = simple_reader('uint64')
read_float32 = simple_reader('float32')
read_float64 = simple_reader('float64')
read_char = simple_reader('char')
read_byte = simple_reader('byte')
read_bool = simple_reader('bool')
