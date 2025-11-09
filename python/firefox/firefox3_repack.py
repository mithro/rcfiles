#!/usr/bin/env python3
#
# This script vacuum's all the firefox sqlite databases. This should make it
# run much faster.

import sys
import sqlite3
import os
import firefox_finder

firefoxdir = firefox_finder.get_profile_dir_interactive()
print("Firefox directory is:", firefoxdir)

locks = ["lock"]
for lock in locks:
  if os.path.exists(os.path.join(firefoxdir, lock)) or os.path.lexists(os.path.join(firefoxdir, lock)):
    print("Firefox running!")
    sys.exit()

for filename in os.listdir(firefoxdir):
  if not filename.endswith(".sqlite"):
    continue
  filename = os.path.join(firefoxdir, filename)
  print("Repacking:", filename)
  sys.stdout.flush()
  before = os.stat(filename).st_size
  s = sqlite3.connect(filename)
  s.execute("VACUUM")
  after = os.stat(filename).st_size
  print("Before %.2fM, after %.2fM" % (before*1.0/1024/1024,
                                       after*1.0/1024/1024))
