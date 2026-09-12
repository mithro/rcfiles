import os
import sys

from progressbar import (
    ETA,
    Bar,
    FileTransferSpeed,
    Percentage,
    ProgressBar,
    RotatingMarker,
)

DEVICE = "/dev/mapper/sysvg-root"

one_mb = 1024 * 1024

widgets = [
    Percentage(),
    " ",
    Bar(marker=RotatingMarker()),
    " ",
    ETA(),
    " ",
    FileTransferSpeed(),
]
i = 0
with open(DEVICE, "rb") as f:
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0, os.SEEK_SET)

    pbar = ProgressBar(widgets=widgets, maxval=size).start()

    while True:
        pbar.update(i * 512)
        pos = f.tell()
        sector = f.read(512)
        if sector.startswith(b"SQLite format 3"):
            print()
            print("Found db at", pos, hex(pos))
            oname = f"{pos}.sqlite3"
            with open(oname, "wb") as out:
                out.write(sector)
                out.write(f.read(one_mb))
            print(oname)
            sys.stdout.flush()
            os.system(f"sqlite3 {oname} .tables")
            print()
            f.seek(-one_mb, os.SEEK_CUR)

        i += 1
        if len(sector) != 512:
            pbar.finish()
            break
