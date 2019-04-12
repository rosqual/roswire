# -*- coding: utf-8 -*-
__all__ = ('BagWriter',)

from typing import BinaryIO, Iterable, Dict

from .core import BagMessage, OpCode, Compression
from ..definitions.encode import *


class BagWriter:
    """
    Provides an interface for writing messages to a bag file on disk.

    Attributes
    ----------
    filename: str
        The name of the file to which the bag will be written.
    """
    def __init__(self, fn: str) -> None:
        self.__fn = fn
        self.__fp: BinaryIO = open(fn, 'wb')

    @property
    def filename(self) -> str:
        return self.__fn

    def _write_header(self, code: OpCode, fields: Dict[str, bytes]) -> None:
        # write a length of zero for now and correct that length once the
        # fields have been written
        pos_size = self.__fp.tell()
        write_uint32(0, self.__fp)
        pos_content = self.__fp.tell()

        fields['op'] = code.value
        for name, bin_value in fields.items():
            bin_name = f'{name}='.encode('utf-8')
            size_field = len(bin_name) + len(bin_value)
            write_uint32(size_field, self.__fp)
            self.__fp.write(bin_name)
            self.__fp.write(bin_value)

        # correct the length
        pos_end = self.__fp.tell()
        size_total = pos_end - pos_content
        self.__fp.seek(pos_size)
        write_uint32(size_total, self.__fp)
        self.__fp.seek(pos_end)

    def _write_header_record(self,
                             pos_index: int,
                             conn_count: int,
                             chunk_count: int
                             ) -> None:
        self.__fp.seek(self.__pos_header)
        self._write_header(OpCode.HEADER,
            {'index_pos': encode_uint64(pos_index),
             'conn_count': encode_uint32(conn_count),
             'chunk_count': encode_uint32(chunk_count)})

        # ensure the bag header record is 4096 characters long by padding it
        # with ASCII space characters (0x20) where necessary.
        pos_current = self.__fp.tell()
        size = 4096
        size_header = pos_current - self.__pos_header
        size_padding = size - size_header - 4

        write_uint32(size_padding, self.__fp)
        padding = b'\x20' * size_padding
        self.__fp.write(padding)

    def _write_chunk(self,
                     compression: Compression,
                     messages: Iterable[BagMessage]) -> None:
        # TODO for now, we only support uncompressed writing
        assert compression == Compression.NONE
        bin_compression = compression.value.encode('utf-8')

        # for now, we write a bogus header and size field
        # once we've finished writing the data, we'll correct them
        pos_header = self.__fp.tell()
        self._write_header(OpCode.CHUNK, {'compression': bin_compression,
                                          'size': encode_uint32(0)})
        write_uint32(0, self.__fp)
        pos_data = self.__fp.tell()

        # TODO write chunk contents
        raise NotImplementedError

        # compute chunk size
        pos_end = self.__fp.tell()
        size_compressed = pos_end - pos_data
        size_uncompressed = size_compressed

        # update header and size
        self.__fp.seek(pos_header)
        self._write_header(OpCode.CHUNK,
            {'compression': bin_compression,
             'size': encode_uint32(size_uncompressed)})
        write_uint32(size_compressed, self.__fp)
        self.__fp.seek(pos_end)

    def write(self, messages: Iterable[BagMessage]) -> None:
        """
        Writes a sequence of messages to the bag.
        Any existing bag file contents will be overwritten.
        """
        self.__fp.write('#ROSBAG V2.0\n'.encode('utf-8'))

        # create a placeholder header for now
        self.__pos_header = self.__fp.tell()
        self._write_header_record(0, 0, 0)

        # for now, we write to a single, uncompressed chunk
        # each chunk record is followed by a sequence of IndexData record
        # - each connection in the chunk is represented by an IndexData record
        self._write_chunk(Compression.NONE, messages)

        # write index
        raise NotImplementedError
