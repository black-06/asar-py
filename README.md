# asar

Library for working with [Electron's ASAR](https://github.com/electron/asar) archive files.

# Installation

```
pip install asar
```

# Usage

- [X] pack and extract asar.
  ```python
  from pathlib import Path
  from asar import create_archive, extract_archive
  
  create_archive(Path("src"), Path("app.asar"))
  extract_archive(Path("app.asar"), Path("dst"))
  ```
- [X] with unpack expression
  ```python
  create_archive(Path("src"), Path("app.asar"), unpack="*.exe")
  ```
  then we got:
  ```
  .
  ├── app.asar
  └── app.asar.unpacked
      └── f2.exe
  ```
- [X] list files of asar
  ```python
  from pathlib import Path
  from asar import AsarArchive
  
  with AsarArchive(Path("app.asar"), mode="r") as archive:
      print(archive.list())
  ```
  then we got:
  ```
  [Path('assets'), Path('assets/icon.png'), ...]
  ```
- [X] read one file from asar by random access
  ```python
  from pathlib import Path
  from asar import AsarArchive
  
  with AsarArchive(Path("app.asar"), mode="r") as archive:
      print(archive.read(Path("f1.txt"), follow_link=True))
  ```
  then we got:
  ```
  b'Hello, Asar'
  ```
- [X] create an asar from another asar, without extracting to filesystem.
  ```python
  import io 
  from pathlib import Path
  from asar import AsarArchive
  
  with AsarArchive(Path("app.asar"), mode="r") as reader, AsarArchive(Path("app.new.asar"), "w") as writer:
      writer.pack_other_asar(reader)
      writer.pack_file(path_in=Path("assets/added1.txt"), file_path=Path("added.txt"))
      writer.pack_stream(path_in=Path("assets/added2.txt"), file_reader=io.BytesIO(b"some text"))
  ```
  then we got app.new.asar, extract it:
  ```
  app_new_asar_extract
          ├── assets
          │     ├── added1.txt
          │     ├── added2.txt
          │     └── ... other files from app.asar 
          └── ... other files from app.asar
  ```