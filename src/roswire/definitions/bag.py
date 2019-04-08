__all__ = ('BagReader',)

from typing import (Dict, Sequence, Union, Optional, Tuple, List, Type,
                    Callable, Collection, Set, Iterator)
from io import BytesIO
from enum import Enum
import os
import bz2
import struct
import datetime
import logging
import heapq

import attr

from .base import Time
from .type_db import Message

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def decode_uint8(v: bytes) -> int:
    return struct.unpack('<B', v)[0]


def decode_uint32(v: bytes) -> int:
    return struct.unpack('<L', v)[0]


def decode_uint64(v: bytes) -> int:
    return struct.unpack('<LL', v)[0]


def decode_str(v: bytes) -> str:
    return v.decode('utf-8')


def decode_time(v: bytes) -> Time:
    return Time(decode_uint32(v[0:4]), decode_uint32(v[4:8]))


class OpCode(Enum):
    MESSAGE_DATA = b'\x02'
    HEADER = b'\x03'
    INDEX_DATA = b'\x04'
    CHUNK = b'\x05'
    CHUNK_INFO = b'\x06'
    CONNECTION_INFO = b'\x07'

    @property
    def hex(self) -> str:
        return f'0x{self.value.hex()}'


class Compression(Enum):
    NONE = 'none'
    BZ2 = 'bz2'


@attr.s(frozen=True, slots=True)
class BagMessage:
    topic: str = attr.ib()
    time: Time = attr.ib()
    # message/data


@attr.s(frozen=True, slots=True)
class ChunkConnection:
    # connection id
    uid: int = attr.ib()
    # number of messages that arrived on this connection in the chunk
    count: int = attr.ib()


@attr.s(frozen=True, slots=True)
class Chunk:
    pos_record: int = attr.ib()
    pos_data: int = attr.ib()
    time_start: Time = attr.ib()
    time_end: Time = attr.ib()
    connections: Tuple[ChunkConnection, ...] = attr.ib(converter=tuple)
    compression: Compression = attr.ib()
    size_uncompressed: int = attr.ib()
    size_compressed: int = attr.ib()


@attr.s(frozen=True, slots=True)
class ConnectionInfo:
    conn: int = attr.ib()
    topic: str = attr.ib()
    topic_original: str = attr.ib()
    typ: str = attr.ib()
    md5sum: str = attr.ib()
    message_definition: str = attr.ib()
    callerid: Optional[str] = attr.ib()
    latching: Optional[str] = attr.ib()


@attr.s(frozen=True, slots=True)
class BagHeader:
    index_pos: int = attr.ib()
    conn_count: int = attr.ib()
    chunk_count: int = attr.ib()


@attr.s(frozen=True, slots=True)
class IndexEntry:
    time: Time = attr.ib()
    pos: int = attr.ib()
    offset: int = attr.ib()


Index = Dict[int, List[IndexEntry]]


class BagReader:
    def __init__(self, fn: str) -> None:
        self.__fp = open(fn, 'rb')
        self.__size_bytes: int = os.path.getsize(fn)

        version = self._read_version()
        assert version == '#ROSBAG V2.0'
        logger.debug("bag version: %s", version)

        self.__header = self._read_header_record()
        logger.debug("bag header: %s", self.__header)

        # skip past chunks
        self._seek(self.__header.index_pos)

        # obtain a list of all connections in the bag
        connections: List[ConnectionInfo] = []
        for i in range(self.__header.conn_count):
            conn = self._read_connection_record()
            connections.append(conn)
        self.__connections: Tuple[ConnectionInfo, ...] = tuple(connections)

        # obtain a summary of each chunk
        chunks: List[Chunk] = []
        for i in range(self.__header.chunk_count):
            info = self._read_chunk_info_record()
            chunks.append(info)
        self.__chunks: Tuple[Chunk, ...] = tuple(chunks)
        self.__pos_to_chunk: Dict[int, Chunk] = \
            {c.pos_record: c for c in chunks}

        # read the index
        self.__index: Index = self._read_index()
        logger.debug("topics: %s", self.topics)
        for conn, indices in self.__index.items():
            logger.debug("conn %d (%s): %d messages",
                         conn, self.__connections[conn].topic, len(indices))

    @property
    def connections(self) -> Tuple[ConnectionInfo, ...]:
        return self.__connections

    @property
    def header(self) -> BagHeader:
        return self.__header

    @property
    def chunks(self) -> Tuple[Chunk, ...]:
        return self.__chunks

    @property
    def index(self) -> Index:
        return self.__index

    @property
    def topics(self) -> Set[str]:
        """The names of all topics represented in this bag."""
        return set(c.topic for c in self.connections)

    def _seek(self, pos: int, ptr=None) -> None:
        ptr = ptr if ptr else self.__fp
        ptr.seek(pos)

    def _skip_sized(self, ptr=None) -> None:
        ptr = ptr if ptr else self.__fp
        ptr.seek(self._read_uint32(), os.SEEK_CUR)

    def _skip_record(self, ptr=None) -> None:
        self._skip_sized(ptr)
        self._skip_sized(ptr)

    def _read_sized(self, ptr=None) -> bytes:
        ptr = ptr if ptr else self.__fp
        size = self._read_uint32(ptr)
        logger.debug("reading sized block: %d bytes", size)
        return ptr.read(size)

    def _read_time(self, ptr=None) -> Time:
        ptr = ptr if ptr else self.__fp
        return decode_time(ptr.read(8))

    def _read_uint32(self, ptr=None) -> int:
        ptr = ptr if ptr else self.__fp
        return decode_uint32(ptr.read(4))

    def _read_version(self, ptr=None) -> str:
        ptr = ptr if ptr else self.__fp
        return decode_str(ptr.readline()).rstrip()

    def _read_header(self,
                     op_expected: Optional[OpCode] = None,
                     *,
                     ptr=None
                     ) -> Dict[str, bytes]:
        fields: Dict[str, bytes] = {}
        header = self._read_sized(ptr)
        while header:
            size = decode_uint32(header[:4])
            header = header[4:]
            name, sep, value = header[:size].partition(b'\x3d')
            if sep == '':
                raise Exception('error reading header field')
            fields[decode_str(name)] = value
            header = header[size:]
        if op_expected:
            assert 'op' in fields
            op_actual: OpCode = OpCode(fields['op'])
            if fields['op'] != op_expected.value:
                m = ("unexpected opcode when reading header: "
                     f"expected {op_expected.name} [{op_expected.hex}] "
                     f"but was {op_actual.name} [{op_actual.hex}].")
                raise Exception(m)
        return fields

    def _read_header_record(self) -> BagHeader:
        header = self._read_header(OpCode.HEADER)
        index_pos = decode_uint64(header['index_pos'])
        conn_count = decode_uint32(header['conn_count'])
        chunk_count = decode_uint32(header['chunk_count'])
        self._skip_sized()
        return BagHeader(index_pos, conn_count, chunk_count)

    def _read_connection_record(self) -> ConnectionInfo:
        header = self._read_header(OpCode.CONNECTION_INFO)
        conn = self._read_header()
        callerid: Optional[str] = None
        latching: Optional[str] = None
        if 'callerid' in conn:
            callerid = decode_str(conn['callerid'])
        if 'latching' in conn:
            latching = decode_str(conn['latching'])
        return ConnectionInfo(conn=decode_uint32(header['conn']),
                              callerid=callerid,
                              latching=latching,
                              topic=decode_str(header['topic']),
                              topic_original=decode_str(conn['topic']),
                              typ=decode_str(conn['type']),
                              md5sum=decode_str(conn['md5sum']),
                              message_definition=decode_str(conn['message_definition']))  # noqa

    def _read_chunk_info_record(self):
        header = self._read_header(OpCode.CHUNK_INFO)
        ver: int = decode_uint32(header['ver'])
        assert ver == 1
        pos_record: int = decode_uint64(header['chunk_pos'])
        time_start: Time = decode_time(header['start_time'])
        time_end: Time = decode_time(header['end_time'])
        num_connections: int = decode_uint32(header['count'])

        # obtain a summary of the number of messages for each connection
        # represented in this chunk
        connections: List[Tuple[int, int]] = []
        contents: bytes = self._read_sized()
        for i in range(num_connections):
            uid = decode_uint32(contents[0:4])
            count = decode_uint32(contents[4:8])
            connections.append(ChunkConnection(uid, count))
            contents = contents[8:]

        # read connection index records?
        assert not contents

        # read the chunk header
        pos_original = self.__fp.tell()
        self.__fp.seek(pos_record)
        header = self._read_header(OpCode.CHUNK)
        size_uncompressed = decode_uint32(header['size'])
        compression = Compression(decode_str(header['compression']))
        pos_data = self.__fp.tell()

        # determine the compressed size of the chunk data
        size_compressed = self._read_uint32()

        # restore the original position of the read pointer
        self.__fp.seek(pos_original)

        chunk = Chunk(pos_record=pos_record,
                      pos_data=pos_data,
                      time_start=time_start,
                      time_end=time_end,
                      size_uncompressed=size_uncompressed,
                      size_compressed=size_compressed,
                      compression=compression,
                      connections=connections)

        logger.debug("decoded chunk: %s", chunk)
        return chunk

    def _read_index(self) -> Index:
        logger.debug("reading index")
        index: Index = {c.conn: [] for c in self.connections}
        for chunk in self.chunks:
            logger.debug("reading index for chunk: %s", chunk)
            pos = chunk.pos_record
            self._seek(pos)
            self._skip_record()
            for i in range(len(chunk.connections)):
                self._read_index_record(pos, index)
        logger.debug("read index")

        logger.debug("pruning empty connections from index")
        for c in [cc for cc in index if not index[cc]]:
            del index[c]
            # TODO delete connection!
        logger.debug("pruned index")
        return index

    def _read_index_record(self, pos_chunk: int, index: Index) -> None:
        header = self._read_header(OpCode.INDEX_DATA)
        ver = decode_uint32(header['ver'])
        uid = decode_uint32(header['conn'])
        count = decode_uint32(header['count'])
        assert ver == 1

        self._read_uint32()  # skip size
        for i in range(count):
            time = self._read_time()
            offset = self._read_uint32()
            entry = IndexEntry(time=time, pos=pos_chunk, offset=offset)
            index[uid].append(entry)

    def _read_chunk_record(self):
        raise NotImplementedError

    def _get_connections(self,
                         topics: Optional[Collection[str]] = None
                         ) -> Iterator[ConnectionInfo]:
        """Returns an iterator over all connections related to a given topic."""
        if not topics:
            yield from self.connections
        else:
            yield from (c for c in self.connections if c.topic in topics)

    def _get_entries(self,
                     connections: Collection[ConnectionInfo],
                     time_start: Optional[Time] = None,
                     time_end: Optional[Time] = None
                     ) -> Iterator[IndexEntry]:
        entries = [self.__index[c.conn] for c in connections]
        entries = heapq.merge(*entries)
        for entry in entries:
            if time_start and entry.time < time_start:
                continue
            if time_end and entry.time > time_end:
                return
            yield entry

    def fetch_message_data_record(self, pos: int, offset: int) -> BagMessage:
        # find the chunk to which the message belongs
        # read the contents of that chunk to a bytes buffer
        chunk = self.__pos_to_chunk[pos]
        self._seek(chunk.pos_data)
        if chunk.compression == Compression.NONE:
            bfr = BytesIO(self._read_sized())
        else:
            raise NotImplementedError

        # seek position of message data record
        # - skip any preceding connection records
        self._seek(offset, bfr)
        while True:
            header = self._read_header(ptr=bfr)
            op = OpCode(header['op'])
            if op == OpCode.CONNECTION_INFO:
                self._skip_sized(bfr)
                continue
            if op == OpCode.MESSAGE_DATA:
                conn_id = decode_uint32(header['conn'])
                t = decode_time(header['time'])
                break
            m = "unexpected opcode: got {} but expected {}"
            m = m.format(op, OpCode.MESSAGE_DATA)
            raise Exception(m)

        # fetch the topic name and message type
        conn_info = self.__connections[conn_id]
        topic = conn_info.topic
        msg_typ_name = conn_info.typ

        # TODO read and decode message content

        logger.debug("TOPIC: %s (%s)", topic, msg_typ_name)
        msg = BagMessage(topic, t)
        logger.debug(msg)
        return msg

    def read_messages(self,
                      topics: Optional[Collection[str]] = None,
                      time_start: Optional[Time] = None,
                      time_end: Optional[Time] = None
                      ) -> Iterator[BagMessage]:
        conns = set(self._get_connections(topics))
        for entry in self._get_entries(conns, time_start, time_end):
            yield self.fetch_message_data_record(entry.pos, entry.offset)

    def __iter__(self) -> Iterator[BagMesssage]:
        yield from self.read_messages()
