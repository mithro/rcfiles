#!/usr/bin/python2.4
#
# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

class EOFError(IOError):
  pass

class CSVReader(object):

  def __init__(self, file):
    self.f = file
    self.state = self.READING

  def byte(self):
    b = self.f.read(1)
    if len(b) == 0:
      raise EOFError("At end of file")
    return b

  def READING(self, b):
    if b == '"':
      self.state = self.QUOTED
    elif b == ',':
      self.args.append("")
    else:
      self.args[-1] += b

    if self.args[-1][-2:] == '\r\n':
      self.args[-1] = self.args[-1][:-2]
      return True

  def QUOTED(self, b):
    if b == '"':
      self.state = self.UNQUOTED
    else:
      self.args[-1] += b

    if self.args[-1][-3:] == '"\r\n':
      self.args[-1] = self.args[-1][:-3]
      return True

  def UNQUOTED(self, b):
    if b == ',':
      self.args.append("")
      self.state = self.READING
    elif b == '"':
      self.args[-1] += '"'
      self.state = self.QUOTED
    elif b == "\r":
      self.args[-1] += b
      self.state = self.QUOTED
    else:
      self.state = self.RECOVERY
      #raise IOError("Invalid CSV file")

  def RECOVER(self, b):
    if b == ",":
      self.state = self.READING

  def __iter__(self):
    while True:
      self.args = [""]

      while True:
        try:
          b = self.byte()
        except EOFError, e:
          yield self.args
          raise StopIteration

        if self.state(b):
          break

          break
      yield self.args

if __name__ == "__main__":
  from cStringIO import StringIO
  s = StringIO("""\
test,"test",test\r\n\
test,"\r\
\n\t\t", test\r\n\
a,b,"te,st""t\0est"\r\n""")

  print "This CSVReader:"
  for x in CSVReader(s):
    print repr(x)

  s.seek(0)

  import csv
  print "Original csv.CSVReader"
  for x in csv.reader(s):
    print repr(x)
