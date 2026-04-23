import io
import json
import struct
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from asar import create_archive, extract_archive, AsarArchive
from asar.asar import align_int


def _cmp_dir(d1: Path, d2: Path):
    assert d1.is_dir(), f"{d1} must be a dir"
    assert d2.is_dir(), f"{d2} must be a dir"
    d1_files, d2_files = list(d1.rglob("*")), list(d2.rglob("*"))
    assert len(d1_files) == len(d2_files), f"dir {d1} and {d2} is different"
    for f1, f2 in zip(d1_files, d2_files):
        if f1.is_symlink() and f2.is_symlink():
            return f1.resolve().relative_to(d1.resolve()) == f2.resolve().relative_to(d2.resolve())
        if f1.is_dir() and f2.is_dir():
            return f1.name == f2.name
        if f1.is_file() and f2.is_file():
            with f1.open("rb") as sf, f2.open("rb") as df:
                return sf.read() == df.read()
        return False


src, asar, dst = (
    Path("./tests/testdata"),
    Path("./tests/testdata.asar"),
    Path("./tests/output"),
)


def test_create_and_extract_asar():
    create_archive(src, asar, unpack="*.exe")
    shutil.rmtree(dst, ignore_errors=True)
    extract_archive(asar, dst)
    _cmp_dir(src, dst)


def test_list_and_read_asar():
    with AsarArchive(asar, mode="r") as archive:
        pathlist = archive.list()
        assert pathlist == sorted([f.relative_to(src) for f in src.rglob("*")])
        for path in pathlist:
            src_file = src / path
            data = archive.read(path, follow_link=True)
            if src_file.is_dir():
                assert data == b""
                continue
            if src_file.is_symlink():
                src_file = src_file.resolve()
            assert data == src_file.read_bytes(), f"file {path} is different from src"


def test_pack_other_asar():
    new_asar = Path("./tests/testdata.new.asar")
    with (
        AsarArchive(asar, mode="r") as reader,
        AsarArchive(new_asar, mode="w") as writer,
    ):
        writer.pack_other_asar(reader)

    shutil.rmtree(dst, ignore_errors=True)
    extract_archive(new_asar, dst)
    _cmp_dir(src, dst)


def test_pack_file_and_stream():
    added1_path, added2_path = Path("assets/added1.txt"), Path("added2.txt")
    added1_file = src / "f1.txt"
    added2_text = "什么啊".encode("utf-8")
    with AsarArchive(asar, mode="w") as writer:
        writer.pack_file(added1_path, added1_file)
        writer.pack_stream(added2_path, io.BytesIO(added2_text))

    with AsarArchive(asar, mode="r") as reader:
        assert reader.read(added1_path) == added1_file.read_bytes()
        assert reader.read(added2_path) == added2_text


def test_pack_stream_overwrites_existing_file_path_entry():
    overwritten_path = Path("overwrite.txt")
    replacement_data = b"stream wins over file"
    with AsarArchive(asar, mode="w") as writer:
        writer.pack_file(overwritten_path, src / "f1.txt")
        writer.pack_stream(overwritten_path, io.BytesIO(replacement_data))

    with AsarArchive(asar, mode="r") as reader:
        assert reader.read(overwritten_path) == replacement_data


def test_pack_all():
    tmp_asar = Path("./tests/testdata.tmp.asar")
    f3, f4, f5, f6 = (
        Path("hello/f3"),
        Path("hello/f4"),
        Path("hello/f5"),
        Path("hello/f6"),
    )
    with AsarArchive(tmp_asar, mode="w") as writer:
        writer.pack_file(f3, src / "f1.txt")
        writer.pack_stream(f4, io.BytesIO(b"hello"))
    with (
        AsarArchive(tmp_asar, mode="r") as reader,
        AsarArchive(asar, mode="w") as writer,
    ):
        writer.pack(src)
        writer.pack_stream(f5, io.BytesIO(b"test"))
        writer.pack_other_asar(reader)
        writer.pack_file(f6, src / "assets" / "icon.png")
    extract_archive(asar, dst)

    assert (dst / f3).read_bytes() == (src / "f1.txt").read_bytes()
    assert (dst / f4).read_bytes() == b"hello"
    assert (dst / f5).read_bytes() == b"test"
    assert (dst / f6).read_bytes() == (src / "assets" / "icon.png").read_bytes()


def test_read_asar_without_integrity_field():
    broken_asar = Path("./tests/testdata.no-integrity.asar")
    create_archive(src, broken_asar)

    with broken_asar.open("rb") as reader:
        data_size, header_size, header_object_size, header_string_size = struct.unpack("<4I", reader.read(16))
        header = json.loads(reader.read(header_string_size).decode("utf-8"))
        reader.seek(8 + header_size)
        payload = reader.read()

    del header["files"]["f1.txt"]["integrity"]
    header_json = json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    aligned_size = align_int(len(header_json), data_size)
    header_object_size = aligned_size + data_size
    header_size = header_object_size + data_size

    with broken_asar.open("wb") as writer:
        writer.write(struct.pack("<4I", data_size, header_size, header_object_size, len(header_json)))
        writer.write(header_json)
        writer.write(b"\0" * (aligned_size - len(header_json)))
        writer.write(payload)

    with AsarArchive(broken_asar, mode="r") as archive:
        assert archive.read(Path("f1.txt")) == (src / "f1.txt").read_bytes()


def test_pack_other_asar_handles_zero_length_file():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_dir = root / "source"
        source_dir.mkdir()
        (source_dir / "empty.txt").write_bytes(b"")
        source_asar = root / "source.asar"
        copied_asar = root / "copied.asar"

        create_archive(source_dir, source_asar)

        with (
            AsarArchive(source_asar, mode="r") as reader,
            AsarArchive(copied_asar, mode="w") as writer,
        ):
            writer.pack_other_asar(reader)

        with AsarArchive(copied_asar, mode="r") as archive:
            assert archive.read(Path("empty.txt")) == b""


def test_pack_other_asar_can_overwrite_existing_file():
    replaced = Path("f1.txt")
    original_data = (src / "f1.txt").read_bytes()
    replacement_data = b"replaced via pack_other_asar workflow"
    new_asar = Path("./tests/testdata.overwrite.asar")

    with (
        AsarArchive(asar, mode="r") as reader,
        AsarArchive(new_asar, mode="w") as writer,
    ):
        writer.pack_other_asar(reader)
        writer.pack_stream(replaced, io.BytesIO(replacement_data))

    with AsarArchive(new_asar, mode="r") as archive:
        assert archive.read(replaced) == replacement_data
        assert archive.read(Path("assets/icon.png")) == (src / "assets" / "icon.png").read_bytes()
        assert archive.read(Path("f2.exe")) == (src / "f2.exe").read_bytes()
        assert archive.read(Path("f1.txt")) != original_data
