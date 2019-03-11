__all__ = ['Bag']

from typing import Dict
import io


# TODO make immutable
class RecordHeader:
    @classmethod
    def from_byte_stream(cls, s: io.BytesIO) -> 'BagRecord':
        fields: Dict[str, bytes] = {}
        length_header: int = int.from_bytes(s.read(4), 'little')
        offset: int = 4
        while offset < length_header:
            bytes_name: bytes
            value: bytes
            length = int.from_bytes(s.read(4), 'little')
            bytes_name, _, value = s.read(length).partition(0x3d)
            name: str = bytes_name.decode('utf-8')
            fields[name] = value
        return RecordHeader(fields)

    def __init__(self,
                 fields: Dict[str, bytes],
                 size: int
                 ) -> None:
        self.__fields = fields
        self.__size = size

    @property
    def size(self) -> int:
        """
        The size of the header, measured in bytes.
        """
        return self.__size

    def __getitem__(self, name: str) -> bytes:
        """
        Retrieves the value of a given field.
        """
        return self.__fields[name]


class BagRecord:
    @classmethod
    def from_bytes(cls, b: bytes) -> 'BagRecord':
        return cls.from_byte_stream(io.BytesIO(b))

    @classmethod
    def from_byte_stream(cls, s: io.BytesIO) -> 'BagRecord':
        pass

    def __init__(self, header: RecordHeader) -> None:
        self._header = header


class BagHeaderRecord(BagRecord):
    @classmethod
    def from_byte_stream(s: io.BytesIO) -> 'BagHeaderRecord':
        header = RecordHeader.from_byte_stream(s)
        assert header['op'] == 0x03
        len_padding = 4096 - header.size
        s.read(len_padding)
        return BagHeaderRecord(header)

    def __init__(self, header: RecordHeader) -> None:
        super().__init__(header)
        self.__index_pos = int.from_bytes(header['index_pos'], 'little')
        self.__conn_count = int.from_bytes(header['conn_count'], 'little')
        self.__chunk_count = int.from_bytes(header['chunk_count'], 'little')

    @property
    def index_pos(self) -> int:
        """
        Offset of the first record after the chunk section.
        """
        return self.__index_pos

    @property
    def conn_count(self) -> int:
        """
        Number of unique connections in the file.
        """
        return self.__conn_count

    @property
    def chunk_count(self) -> int:
        """
        Number of chunk records in the file.
        """
        return self.__chunk_count


class ChunkRecord(BagRecord):
    pass


class ConnectionRecord(BagRecord):
    pass


class MessageDataRecord(BagRecord):
    pass


class IndexDataRecord(BagRecord):
    pass


class ChunkInfoRecord(BagRecord):
    pass


class Bag:
    @staticmethod
    def from_byte_stream(s: io.BytesIO) -> 'Bag':
        version_line: str = s.readline().decode('utf-8')
        assert version_line == '#ROSBAG V2.0\n'

        header: BagHeader = BagHeader.from_byte_stream(s)

        # parse records

        BagRecord.from_byte_stream(s)

    @staticmethod
    def from_bytes(b: bytes) -> 'Bag':
        return Bag.from_byte_stream(io.BytesIO(b))

    @staticmethod
    def from_file(fn: str) -> 'Bag':
        with open(fn, 'rb') as f:
            return Bag.from_byte_stream(f)

    def __init__(self, header: BagHeader) -> None:
        self.__header: BagHeader = header
