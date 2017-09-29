"""
Simple script to test possible performance regression with different workloads
"""
import os
import sys
from itertools import cycle

from time import time, sleep
from pyrated.ratelimit import RatelimitList


C = 3000000
N = 10
D = 1000
K = '129.28.31.240'

r = RatelimitList(N, D)
s = time()
for i in range(C):
    r.hit(K)
d = time() - s
print('Single key (%d chars), %d entries, %d loops: %.3fs (%d/s)' % (len(K), N, C, d, C / d)) 

N = 2000
r = RatelimitList(N, D)
s = time()
for i in range(C):
    r.hit(K)
d = time() - s
print('Single key (%d chars), %d entries, %d loops: %.3fs (%d/s)' % (len(K), N, C, d, C / d)) 

KEYS = ('10.0.1.20', '15,2.8.4', '192.168.0.4', '9.9.4.1', '244.200.8.1')
IKEYS = KEYS * int(C/len(KEYS))
N = 10
r = RatelimitList(N, D)
s = time()
for k in IKEYS:
    r.hit(k)
d = time() - s
print('%d keys, %d entries, %d loops: %.3fs (%d/s)' % (len(KEYS), N, len(IKEYS), d, len(IKEYS) / d)) 

N = 5000
r = RatelimitList(N, D)
s = time()
for k in IKEYS:
    r.hit(k)
d = time() - s
print('%d keys, %d entries, %d loops: %.3fs (%d/s)' % (len(KEYS), N, len(IKEYS), d, len(IKEYS) / d)) 

KEYS = tuple('1.2.3.%d' % i for i in range(50000))
IKEYS = KEYS * int(C/len(KEYS))
N = 10
r = RatelimitList(N, D)
s = time()
for k in IKEYS:
    r.hit(k)
d = time() - s
print('%d keys, %d entries, %d loops: %.3fs (%d/s)' % (len(KEYS), N, len(IKEYS), d, len(IKEYS) / d)) 

N = 5000
r = RatelimitList(N, D)
s = time()
for k in IKEYS:
    r.hit(k)
d = time() - s
print('%d keys, %d entries, %d loops: %.3fs (%d/s)' % (len(KEYS), N, len(IKEYS), d, len(IKEYS) / d)) 
