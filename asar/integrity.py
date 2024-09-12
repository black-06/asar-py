"""
integrity is an object consisting of a few keys:

- A hashing algorithm, currently only SHA256 is supported.
- A hex encoded hash value representing the hash of the entire file.
- An array of hex encoded hashes for the blocks of the file. i.e. for a blockSize of 4KB this array contains the hash of every block if you split the file into N 4KB blocks.
- A integer value blockSize representing the size in bytes of each block in the blocks hashes above
"""

import hashlib
from pathlib import Path
from typing import BinaryIO, Dict, Any, Tuple

ALGORITHM = "SHA256"
BLOCK_SIZE = 4 * 1024 * 1024


def get_file_integrity(file_path: Path) -> Dict[str, Any]:
    """
    Calc the integrity of a file.
    :param file_path: The file path.
    :return: integrity
    """
    with file_path.open("rb") as reader:
        return get_reader_integrity(reader)[0]


def get_reader_integrity(reader: BinaryIO) -> Tuple[Dict[str, Any], int]:
    """
    Calc the integrity of a file stream.
    :param reader: Input file stream, it should be readable and seekable.
    :return: (integrity, size)
    """
    hasher = hashlib.sha256()
    blocks = []
    size = 0
    reader.seek(0)
    while chunk := reader.read(BLOCK_SIZE):
        size += len(chunk)
        hasher.update(chunk)
        blocks.append(hashlib.sha256(chunk).hexdigest())
    return {
        "algorithm": ALGORITHM,
        "hash": hasher.hexdigest(),
        "blockSize": BLOCK_SIZE,
        "blocks": blocks,
    }, size
