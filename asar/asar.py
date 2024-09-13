"""
Asar is a simple extensive archive format for Electron Archive, it works like tar that concatenates all files
together without compression, while having random access support.
"""

import fnmatch
import json
import shutil
import struct
from pathlib import Path
from typing import Dict, Any, BinaryIO, List

from .limited_reader import LimitedReader
from .metadata import Metadata, Type

UINT32_MAX = 2 ** 32 - 1


def align_int(i: int, alignment: int) -> int:
    """
    Align i to alignment, same as `i + (alignment - (i % alignment))`
    """
    return (i + alignment - 1) & ~(alignment - 1)


_modes = {"r": "rb", "w": "wb"}


class AsarArchive:
    """
    Class with methods to open, read, write, close asar files.
    """
    asar: Path
    asar_unpacked: Path
    _asar_io: BinaryIO
    _mode: str
    _header: Metadata
    _offset: int
    metas: List[Metadata]

    def __init__(self, asar: Path, mode: str):
        """
        Open the asar file with mode read 'r', write 'w'
        :param asar: the asar file path
        :param mode: read 'r' or write 'w'
        """
        self.asar = asar
        self.asar_unpacked = Path(f"{self.asar}.unpacked")
        self._mode = mode
        self._header = Metadata(path=Path(""), type=Type.DIRECTORY, files={})
        self.metas = []
        self._offset = 0
        if self._mode not in _modes:
            raise ValueError("AsarArchive requires mode 'r' or 'w'")
        # noinspection PyTypeChecker
        self._asar_io = self.asar.open(_modes[self._mode])

    def __enter__(self):
        if self._mode == "r":
            self._read_from_asar()
        return self

    def __exit__(self, *args):
        if self._mode == "w":
            self._write_to_asar()
        self._asar_io.close()

    def list(self):
        """Return a list of file paths in the archive."""
        return [meta.path for meta in self.metas]

    def pack_other_asar(self, other: "AsarArchive"):
        for meta in other.metas:
            node = self._search_node_from_path(meta.path)
            node.set_from_other(meta)
            if meta.type == Type.DIRECTORY:
                continue
            if meta.type == Type.FILE and not meta.unpacked:
                node.offset = self._offset
                self._offset += node.size

    def pack(self, src: Path, unpack: str = None):
        """
        Add all files from src path to the asar archive.
        :param src: src path
        :param unpack: do not pack files matching glob <expression>
        """
        if not src:
            raise ValueError("src path not provided")
        if not src.is_absolute() or src.is_symlink():
            src = src.resolve()
        for path in src.iterdir():
            self._pack(path, src, unpack)

    def _pack(self, path: Path, src: Path, unpack: str):
        path_in = path.relative_to(src)
        if path.is_symlink():
            node = self._search_node_from_path(path_in)
            node.set_link(path.resolve().relative_to(src))
            if node.link.parts[0] == "..":
                raise ValueError(f'${path_in}: file "{node.link}" links out of the package')
        elif path.is_dir():
            node = self._search_node_from_path(path_in)
            node.set_dir(unpacked=unpack and fnmatch.fnmatch(path.name, unpack))
            for child in path.iterdir():
                self._pack(child, src, unpack)
        else:
            self.pack_file(path_in, path, should_unpack=unpack and fnmatch.fnmatch(path.name, unpack))

    def pack_stream(self, path_in: Path, file_reader: BinaryIO, should_unpack: bool = False):
        """
        Add one file stream to the asar archive.
        :param path_in: the path in asar archive.
        :param file_reader: the file stream.
        :param should_unpack: unpacked in asar? If not packed, it will be written to unpacked path
        :return:
        """
        dir_node = self._search_node_from_path(path_in.parent)
        node = self._search_node_from_path(path_in)
        node.set_stream(file_reader, unpacked=dir_node.unpacked or should_unpack)
        if not node.unpacked:
            if node.size > UINT32_MAX:
                raise ValueError(f"{path_in}: file size can not be larger than 4.2GB")
            node.offset = self._offset
            self._offset += node.size

    def pack_file(self, path_in: Path, file_path: Path, should_unpack: bool = False):
        """
        Add one file to the asar archive.
        :param path_in: the path in asar archive.
        :param file_path: the actual file path.
        :param should_unpack: unpacked in asar? If not packed, it will be written to unpacked path
        """
        dir_node = self._search_node_from_path(path_in.parent)
        node = self._search_node_from_path(path_in)
        node.set_file(file_path, unpacked=dir_node.unpacked or should_unpack)
        if not node.unpacked:
            if node.size > UINT32_MAX:
                raise ValueError(f"{path_in}: file size can not be larger than 4.2GB")
            node.offset = self._offset
            self._offset += node.size

    def read(self, path_in: Path, follow_link: bool = True):
        """
        Read one file from asar by random access
        :param path_in: path in asar
        :param follow_link: read the actual file if the path is a link
        :return: file bytes
        """
        node = self._search_node_from_path(path_in, create=False)
        if node.type == Type.DIRECTORY:
            return b""
        elif node.type == Type.LINK:
            return self.read(node.link) if follow_link else b""
        elif node.unpacked:
            if not node.file_path.exists():
                raise FileNotFoundError(node.file_path)
            with node.file_path.open("rb") as reader:
                return reader.read()
        else:
            node.file_reader.seek(0)
            return node.file_reader.read()

    def extract(self, dst: Path = None):
        """
        Extract the asar archive to the dst path.
        :param dst: dst dir path
        """
        dst = dst if dst else Path.cwd()
        dst.mkdir(parents=True, exist_ok=True)
        if not dst.is_absolute() or dst.is_symlink():
            dst = dst.resolve()
        for meta in self.metas:
            cur_dst = dst / meta.path
            if meta.type == Type.DIRECTORY:
                cur_dst.mkdir(parents=True, exist_ok=True)
            elif meta.type == Type.LINK:
                src_link = dst / meta.link
                try:
                    cur_dst.symlink_to(src_link)
                except FileExistsError:
                    cur_dst.unlink()
                    cur_dst.symlink_to(src_link)
            elif meta.unpacked:
                if not meta.file_path.exists():
                    raise FileNotFoundError(meta.file_path)
                shutil.copyfile(meta.file_path, cur_dst)
            else:
                with cur_dst.open(mode="wb") as writer:
                    meta.file_reader.seek(0)
                    shutil.copyfileobj(meta.file_reader, writer)

    def _read_from_asar(self):
        data_size, header_size, header_object_size, header_string_size = struct.unpack("<4I", self._asar_io.read(16))
        header = json.loads(self._asar_io.read(header_string_size).decode("utf-8"))
        self._offset = 8 + header_size
        self._parse_metadata(header, Path(""))

    def _parse_metadata(self, info: Dict[str, Any], path_in: Path):
        for name, child in info["files"].items():
            cur_path = path_in / name
            node = self._search_node_from_path(cur_path)
            if "files" in child:
                node.set_dir("unpacked" in child and bool(child["unpacked"]))
                self._parse_metadata(child, cur_path)
            elif "link" in child:
                node.set_link(Path(child["link"]))
            else:
                node.unpacked = "unpacked" in child and bool(child["unpacked"])
                node.type = Type.FILE
                node.integrity = child["integrity"]
                node.size = child["size"]
                if node.unpacked:
                    node.file_path = self.asar_unpacked / node.path
                else:
                    node.offset = int(child["offset"])
                    node.file_reader = LimitedReader(self._asar_io, self._offset + node.offset, node.size)

    def _write_to_asar(self):
        header_json = json.dumps(self._header.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        header_json = header_json.encode("utf-8")
        data_size = 4
        header_string_size = len(header_json)
        aligned_size = align_int(header_string_size, data_size)
        header_object_size = aligned_size + data_size
        header_size = header_object_size + data_size
        self._asar_io.write(struct.pack("<4I", data_size, header_size, header_object_size, header_string_size))
        self._asar_io.write(header_json)
        self._asar_io.write(b'\0' * (aligned_size - header_string_size))
        for metadata in self.metas:
            if metadata.type != Type.FILE:
                continue
            if metadata.unpacked:
                dst = self.asar_unpacked / metadata.path
                dst.parent.mkdir(parents=True, exist_ok=True)
                if metadata.file_path:
                    shutil.copyfile(metadata.file_path, dst)
                elif metadata.file_reader:
                    with dst.open("wb") as writer:
                        metadata.file_reader.seek(0)
                        shutil.copyfileobj(metadata.file_reader, writer)
            else:
                if metadata.file_path:
                    with open(metadata.file_path, "rb") as reader:
                        shutil.copyfileobj(reader, self._asar_io)
                elif metadata.file_reader:
                    metadata.file_reader.seek(0)
                    shutil.copyfileobj(metadata.file_reader, self._asar_io)

    def _search_node_from_path(self, path_in: Path, create: bool = True) -> Metadata:
        node = self._header
        name = path_in.name
        if not name:
            return node
        for part in path_in.parent.parts:
            if part != ".":
                node = node.files[part]
        if node.files.get(name) is None:
            if create:
                metadata = Metadata(path=path_in)
                node.files[name] = metadata
                self.metas.append(metadata)
            else:
                raise FileNotFoundError(path_in)
        return node.files[name]


def create_archive(dir_path: Path, asar_path: Path, unpack: str = None):
    """
    Pack the dir to create an asar archive.
    :param dir_path: The dir to pack.
    :param asar_path: The output asar path.
    :param unpack: do not pack files matching glob <expression>
    """
    with AsarArchive(asar_path, "w") as asar:
        asar.pack(dir_path, unpack)


def extract_archive(asar_path: Path, dir_path: Path):
    """
    Extract the asar archive to the dir.
    :param asar_path: The asar archive path to extract.
    :param dir_path: The output dir path.
    """
    with AsarArchive(asar_path, "r") as asar:
        asar.extract(dir_path)
