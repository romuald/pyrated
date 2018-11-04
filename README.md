# pyrated - Python Ratelimit Daemon

pyrated is a server (and a library) that can be used to constraint queries made to a specific rate


The daemon is using the memcached TCP protocol as a base so you can use any memcached client to connect to it


### Simple example

Launching the daemon to limit clients to 10 queries per minute:

```
% pyrated 10/1m
Serving on 127.0.0.1, ::1, fe80::1 - port 11211
```


After that, using a memcache client:

```python
client = memcache.Client(['localhost'])

assert client.incr('foo') == 0

checks = [client.incr('foo') for _ in range(10)]
assert checks == [0, 0, 0, 0, 0, 0, 0, 0, 0, 1]  # 1 = limit reached

assert client.incr('bar') == 0

sleep(59)
assert client.incr('foo') == 1

sleep(1)
assert client.incr('foo') == 0
```


Note that the logic is kind of reversed, the server replies with a "positive"
answer only when the limit has been reached.

This is done to allow applications to gracefully fall back to allowing
requests when the server is unavailable, since most memcached clients
will return a *NULL* value in that case.

For example:

```python
if client.incr(environ['REMOTE_ADDR']):
    abort(429)
```

### Library

*(TODO, add some examples for the library code)*


### Details

The ratelimit made to enforce that no more than X of hits are made within a specific time frame.

Given the 10 queries / minute initial example, if a client makes 9 hits in the first second, then 1 hit on the 20th second, all subsequent hits will fail (but won't *punish* the client for trying).

Once one minute and one second is elapsed, the client will gain 9 "slots", and 20 seconds later will gain a 10th (if he did not make any more call)

*(TODO, illustrate this with an animation)*

----------

The ratelimit logic is implemented in C for both performance and memory usage (since all timestamps are stored, the difference is very noticeable if you have a high query limit)

The precision of the timestamps is millisecond, the maximum time frame allowed is 45 days


### Command line options

`pyrated -s localhost -s mylocalname -p 10001 500/1h`

The ratelimit definition is *$queries*/*$timespec*, and the timespec is *$number$unit* with unit being [m]inutes, [h]ours or [d]ays, or seconds with no letter

- **-s**, **--source** the source IP/name to listen to. Might be used more than once (default: *localhost*)
- **-p**, **--port** the TCP port to listen to (default: *11211*)

