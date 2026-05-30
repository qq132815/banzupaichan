# -*- coding: utf-8 -*-
import os

BASE = os.getcwd()
TPL = os.path.join(BASE, chr(116)+chr(101)+chr(109)+chr(112)+chr(108)+chr(97)+chr(116)+chr(101)+chr(115))

def w(name, lines):
    path = os.path.join(TPL, name)
    with open(path, chr(119), encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)) as f:
        f.write(chr(10).join(lines))
    print(chr(67)+chr(114)+chr(101)+chr(97)+chr(116)+chr(101)+chr(100)+chr(32)+name)

print(chr(83)+chr(116)+chr(97)+chr(114)+chr(116))
