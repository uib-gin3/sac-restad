# restad REST Daemon that knows how to "restar"

- Rest -> Application Programming Interface y Representational State Transfer
- Resta -> Substract in spanish
- Restad -> Plural of substract in spanish (imperative).

Unix daemons finalize with a `d`: we ask a bunch of unix processes running as
a daemon to act as a REST API able to `restar`, so unix processes `restad` this
numbers.


## Abstract

A simple REST API implemented with Python + Bottle to implement a basic
calculator. Restad can run by itself as a single python process, multiprocess
with gunicorn and opionally use Redis as backend when deployed in different
containers / servers.

The development has been done following KISS (Keep it Simple Stupid) and UNIX
philosophy (do one thing and do it well). As Redis already needed a container
a Dockerfile and docker-compose.yml has been added as well.


## Assignment

Implement a **calculator** as a REST service, in any language you choose:
  add, sub, div, mult, sqrt, mean, std and reset.

The user must keep their last value, which is why the special `reset` operation
exists.

Justify the design and implementation decisions taken under the SD (shared-state)
paradigm.

**Delivery**: in AD (the campus delivery system), include the link to the (publicly
accessible) repository containing the source code and the relevant descriptions.


## Setup

This project has been tested on Debian 13 and docker 29.9.0 with the compose plugin.

It should just be needed bash, docker and docker compose.

If running without Redis containers can be avoided and used uv / uvx. Tested with 0.11.8.


## Usage example

### Some useful alias

    alias GET="uvx --from httpie http GET"
    alias POST="uvx --from httpie http POST"
    alias PUT="uvx --from httpie http PUT"
    alias PATCH="uvx --from httpie http PATCH"
    alias DELETE="uvx --from httpie http DELETE"

### Run simple way: single process no redis

    uv run --with bottle==0.13.4 python app.py

### Production mode: multiprocess with gunicorn + redis

    docker compose up

### Test

    PUT localhost:12345/calc/my-calc --raw 3,4,5,6
    PATCH localhost:12345/calc/my-calc --raw 7,8,9
    GET localhost:12345/calc/my-calc/add
    # Will respond the meaning of life (42)

### Benchmark

   uv run ./restad-bench -c 5 -r 10 -d 30


Without uv is also fine as restad-bench is all python stdlib.


## Server interface

Tried to follow HTTP Verb sematincs https://www.rfc-editor.org/rfc/rfc9110.html

Create a calculus with POST, you can send the first list of numbers in the payload:

    POST localhost:12345/calc --raw 3,4,5,6
    # Will return the calc-id as response and in the Location header

You can also create a calculus by PUTing all the content into the id you define.

    PUT localhost:12345/calc/my-calc --raw 3,4,5,6

Numbers can be added with PATCH

    PATCH localhost:12345/calc/my-calc --raw 7,8,9
    # <some-id> will contain the list 3,4,5,6,7,8,9


You alse can can GET the result (without modifing the calc) appending an operation

    GET localhost:12345/calc/my-calc/add
    # Will respond 42

You can also GET the content without an operation, it just responds the number list.

    GET localhost:12345/calc/my-calc
    # Will respond 3,4,5,6,7,8,9

We can get the result as well POSTing it into a consolidated result:

    POST localhost:12345/calc/my-calc/add
    # Will respond 42

    GET localhost:12345/calc/my-calc
    # Will respond 42 not the number list

Finally you can DELETE the calc when no longer needed.

    DELETE localhost:12345/calc/my-calc
    # Will delete it

    GET localhost:12345/calc/my-calc
    # Will respond 404


## Design decisions

No versioning for the REST API, is too simple.

Normally I would go Flask or Django RESTframework but will go even simpler
with `bottle`.

JSON si really popular on REST APIS but is just a convetion, is not really
needed, this API si not JSON, just plain strings. Numbers can be separated by
commas to be lists.

To avoid a collisions used a hash based on timestamp + source ip + source
port + some randomness. Hash function selected djb2, not becuase the best just
becuse DJB is awesome and always deserve credit.

The implementation has a dual way to operate with standard python shared
memory or Redis. Locks also suport both backends.

Let's imagine an entity which is 'number list' so tryied to understand verbs
from https://www.rfc-editor.org/rfc/rfc9110.html and use them properly on it.


## Observations

Table run and generated with MiniMax M3.1 OpenCode when asked to compare
sac-restad with sac-sock-mon

|                             | socket `sac-sock-calc` | REST bottle (1 process) | REST gunicorn 4w + redis  |
|-----------------------------|------------------------|-------------------------|---------------------------|
| offered load                | 50 req/s               | 50 ops/s (150 req/s)    | 50 ops/s (150 req/s)      |
| served                      | 1313 req (43.7 req/s)  | 1475 ops / 4425 req     | 1373 ops / 4119 req       |
| throughput                  | 43.7 req/s             | 49.2 ops/s (147.5 req/s)| 45.8 ops/s (137.3 req/s)  |
| errors                      | 0                      | 0                       | 0                         |
| TCP connections             | 5 (one per client)     | 4425 (one per request)  | 4119 (one per request)    |
| response time p50           | 4.30 ms                | 1.67 ms                 | 2.35 ms                   |
| response time p95           | 44.91 ms               | 2.54 ms                 | 3.26 ms                   |
| response time p99           | 47.63 ms               | 3.24 ms                 | 3.63 ms                   |
| response time max           | 50.36 ms               | 4.56 ms                 | 7.10 ms                   |
| server's own clock (avg/p95)| 0.53 / 1.91 ms         | 0.42 / 0.70 ms          | 0.65 / 1.00 ms            |
| bytes sent / received       | 127 249 / 27 658       | 455 803 / 871 245       | 427 158 / 777 238         |

I have to confess that I'm not double checking it to arrive on the delivery
deadline.

Seeing that result I would say:

- Even sac-sock-mon have less layers it was poorly implemented and optimized
so gnuigorn is a way faster even having a way more layers.
- There are no significant diferences between single python process and
multiprocess with gunicorn problably the bottleneck is the benchmark client itself.
- Redis and gunicorn seem to increase reasponse time. More layers more ms,
but not crazy at all. With bigger requests wont be noticable.

## AI usage

None of the text intended to be read by a human has been generated or processed
by any AI tool, whereas most of the texts (code) intended to be processed by a
machine have been generated by AI Agents (OpenCode)

Nowadays it is extremely easy to produce tons of text. I could ask OpenCode to
write this file and look amazing, but I've tried to keep the assignment within
its bounds to just show the ability to use sockets and put some thought into
using them.

AI tools have been used to check spelling and grammar but never to be
copy-pasted: instead, the mistakes are understood and edited manually in the
original text.

This approach is to avoid being a [meat proxy](https://gruhn.me/blog/2026-08-03/).

- gemini-3.1-pro (web): Translate <assignment title> to English
- gemini-3.1-pro (web): Many lookups of information about python libraries
and REST concepts
- gemini-3.1-pro (web): Implement djb2 hash function
- MiniMax-M3.1-flash (opencode): Develop restad-client, restad-test,
restad-bench & restadapi.py
- MiniMax-M3.1-flash (opencode): Run benchmark to compare sac-sock-calc
and sac-restad
- MiniMax-M3.1-flash (opencode): Can you check spell and grammar of README.md.
Suggest the minimal changes keeping the style.
- MiniMax-M3.1-flash (opencode): Can you check spell and grammar of the
comments of (not code) of restad-server. Suggest the minimal changes keeping
the style.
