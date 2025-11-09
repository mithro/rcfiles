
import os
import sys
from progressbar import *

f = open('/dev/mapper/sysvg-root', 'rb')
f.seek(0, os.SEEK_END)
size = f.tell()
f.seek(0, os.SEEK_SET)

one_mb = 1024*1024

widgets = [Percentage(), ' ', Bar(marker=RotatingMarker()), ' ', ETA(), ' ', FileTransferSpeed()]
pbar = ProgressBar(widgets=widgets, maxval=size).start()

i = 0
while True:
    pbar.update(i*512)
    pos = f.tell()
    sector = f.read(512)
    if sector.startswith(b"SQLite format 3"):
        print()
        print("Found db at", pos, hex(pos))
        oname = '%s.sqlite3' % pos
        out = open(oname, 'wb')
        out.write(sector)
        out.write(f.read(one_mb))
        out.close()
        print(oname)
        sys.stdout.flush()
        os.system('sqlite3 %s .tables' % oname)
        print()
        f.seek(-one_mb, os.SEEK_CUR)

    i += 1
    if len(sector) != 512:
        pbar.finish()
        break
