#!/usr/bin/env python3
#
# Copyright 2009 Google Inc.
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

# FIXME: This could be done better...
DOUBLEWIDTH = 0x2DFF


def termwidth(s):
    """\
    Calculate the width of a string on a fixed with terminal.

    (It works on the theory that any character with a unicode value above
    DOUBLEWIDTH takes two spaces to be rendered.)
  """
    width = 0
    for c in s:
        if ord(c) > DOUBLEWIDTH:
            width += 2
        else:
            width += 1
    return width


def spacesplit(input):
    """\
    This function splits works like normal split except that it keeps any extra
    white space with the previous bit. For example:

    'sdfas sadfsdf sad    sadfdsf'
        converts to
    ['sdfas', 'sadfsdf', 'sad    ', 'sadfdsf']

    FIXME: This should probably match on any whitespace not just " "
  """
    w = []
    for bit in input.split(" "):
        if len(bit) == 0:
            w[-1] += " "
        else:
            w.append(bit)
    return w


def match(left, right):
    """\
    match tries to make each element in the right list the same length as
    each element in the left list. It does this by manipulating trailing
    white space.
  """
    newright = []
    for a, b in zip(left, right):
        b = b.strip()

        diff = len(a) - len(b)
        if diff > 0:
            b = b + " " * diff
        newright.append(b)
    return newright


def lines(input):
    """\
    lines is a generator that works exactly like readlines() except it is more
    reliable with crappy input.
  """
    while True:
        b = " "
        while b[-1] != "\n":
            w = input.read(1)
            if len(w) == 0:
                yield b[1:-1]
                raise StopIteration
            b += w
        yield b[1:-1]
