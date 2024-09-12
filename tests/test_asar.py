import io
import shutil
from pathlib import Path

from asar import create_archive, extract_archive, AsarArchive


def cmp(f1: Path, f2: Path) -> bool:
    if f1.is_symlink() and f2.is_symlink():
        return f1.resolve().relative_to(src.resolve()) == f2.resolve().relative_to(dst.resolve())
    if f1.is_dir() and f2.is_dir():
        return f1.name == f2.name
    if f1.is_file() and f2.is_file():
        with f1.open("rb") as sf, f2.open("rb") as df:
            return sf.read() == df.read()
    return False


if __name__ == '__main__':
    src, asar, dst = Path("./testdata"), Path("./testdata.asar"), Path("./output")
    create_archive(src, asar, unpack="*.exe")
    shutil.rmtree(dst, ignore_errors=True)
    extract_archive(asar, dst)

    src_files, dst_files = list(src.rglob("*")), list(dst.rglob("*"))
    assert len(src_files) == len(dst_files)
    for s, d in zip(src_files, dst_files):
        assert s.relative_to(src) == d.relative_to(dst)
        assert cmp(s, d), f"file {s} and {d} is different"

    with AsarArchive(asar, mode="r") as archive:
        pathlist = archive.list()
        assert pathlist == sorted([f.relative_to(src) for f in src_files])
        for path in pathlist:
            src_file = src / path
            if src_file.is_dir():
                continue
            if src_file.is_symlink():
                src_file = src_file.resolve()
            assert src_file.read_bytes() == archive.read(path, follow_link=True), f"file {path} is different from src"

        new_asar = Path("./testdata.new.asar")
        added1_path, added2_path = Path("assets/added1.txt"), Path("assets/added2.txt")
        added2_text = "什么啊"

        with AsarArchive(new_asar, mode="w") as writer:
            writer.pack_other_asar(archive)
            writer.pack_file(path_in=added1_path, file_path=src / "f1.txt")
            writer.pack_stream(path_in=added2_path, file_reader=io.BytesIO(added2_text.encode("utf-8")))

    shutil.rmtree(dst, ignore_errors=True)
    extract_archive(new_asar, dst)

    assert cmp(src / "f1.txt", dst / added1_path)
    assert (dst / added2_path).read_text(encoding="utf-8") == added2_text

    src_files, dst_files = list(src.rglob("*")), list(dst.rglob("*"))
    dst_files.remove(dst / added1_path)
    dst_files.remove(dst / added2_path)
    assert len(src_files) == len(dst_files)
    for s, d in zip(src_files, dst_files):
        assert s.relative_to(src) == d.relative_to(dst)
        assert cmp(s, d), f"file {s} and {d} is different"
