import io
import shutil
from pathlib import Path

from asar import create_archive, extract_archive, AsarArchive


def _cmp_dir(d1: Path, d2: Path):
    assert d1.is_dir(), f"{d1} must be a dir"
    assert d2.is_dir(), f"{d2} must be a dir"
    d1_files, d2_files = list(d1.rglob("*")), list(d2.rglob("*"))
    assert len(d1_files) == len(d2_files), f"dir {d1} and {d2} is different"
    for f1, f2 in zip(d1_files, d2_files):
        if f1.is_symlink() and f2.is_symlink():
            return f1.resolve().relative_to(d1.resolve()) == f2.resolve().relative_to(
                d2.resolve()
            )
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
    with AsarArchive(asar, mode="r") as reader, AsarArchive(
        new_asar, mode="w"
    ) as writer:
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
    with AsarArchive(tmp_asar, mode="r") as reader, AsarArchive(
        asar, mode="w"
    ) as writer:
        writer.pack(src)
        writer.pack_stream(f5, io.BytesIO(b"test"))
        writer.pack_other_asar(reader)
        writer.pack_file(f6, src / "assets" / "icon.png")
    extract_archive(asar, dst)

    assert (dst / f3).read_bytes() == (src / "f1.txt").read_bytes()
    assert (dst / f4).read_bytes() == b"hello"
    assert (dst / f5).read_bytes() == b"test"
    assert (dst / f6).read_bytes() == (src / "assets" / "icon.png").read_bytes()
