import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Union, BinaryIO

from .integrity import get_file_integrity, get_reader_integrity
from .limited_reader import LimitedReader


class Type(Enum):
    """
    File Type
    """
    DIRECTORY = 1
    LINK = 2
    FILE = 3


@dataclass
class Metadata:
    """
    File metadata stored in the header.
    """
    # path in asar file
    path: Path
    type: Type = None
    # directory
    files: Dict[str, "Metadata"] = None
    # link
    link: Path = None
    # file
    unpacked: bool = False
    size: int = 0
    offset: int = 0
    integrity: Dict[str, Any] = None
    executable: bool = False
    # real file path or stream to read
    file_path: Path = None
    file_reader: Union[BinaryIO, LimitedReader] = None

    def set_link(self, link_in: Path):
        """
        Set the node as a link node
        :param link_in: the target path to which the symbolic link points
        """
        self.type = Type.LINK
        self.link = link_in

    def set_dir(self, unpacked: bool):
        """
        Set the node as a directory node
        :param unpacked: Exclude from packaging?
        """
        self.unpacked = unpacked
        self.type = Type.DIRECTORY
        self.files = {}

    def set_file(self, file_path: Path, unpacked: bool):
        """
        Set the node as a file node
        :param file_path: The actual file path, through which we read file size and data
        :param unpacked: Exclude from packaging?
        """
        self.unpacked = unpacked
        self.type = Type.FILE
        stat = file_path.stat()
        self.size = stat.st_size
        self.integrity = get_file_integrity(file_path)
        self.file_path = file_path
        self.executable = os.name != "nt" and (stat.st_mode & 0o100)

    def set_stream(self, file_reader: Union[BinaryIO, LimitedReader], unpacked: bool):
        """
        Set the node as a file stream node
        :param file_reader: The actual file stream, through which we read file size and data
        :param unpacked: Exclude from packaging?
        """
        self.unpacked = unpacked
        self.type = Type.FILE
        self.integrity, self.size = get_reader_integrity(file_reader)
        self.file_reader = file_reader

    def set_from_other(self, other: "Metadata"):
        """
        Set the node from other metadata, but not including files and offset
        :param other:
        """
        self.path = other.path
        self.type = other.type
        if self.type == Type.LINK:
            self.link = other.link
        elif self.type == Type.DIRECTORY:
            self.unpacked = other.unpacked
        else:
            self.unpacked = other.unpacked
            self.size = other.size
            self.integrity = other.integrity
            self.executable = other.executable
            self.file_path = other.file_path
            self.file_reader = other.file_reader

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to a formatted dict, usually the next step is to serialize to json
        """
        if self.type == Type.DIRECTORY:
            files = {}
            for key, value in self.files.items():
                files[key] = value.to_dict()
            return {"files": files}

        if self.type == Type.LINK:
            return {"link": str(self.link)}

        rst = {"size": self.size, "integrity": self.integrity}
        if self.unpacked:
            rst["unpacked"] = self.unpacked
        else:
            rst["offset"] = str(self.offset)
        if self.executable:
            rst["executable"] = self.executable
        return rst
