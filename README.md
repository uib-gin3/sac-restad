# restad REST Daemon that knows how to "restar"

Rest -> Application Programming Interface y Representational State Transfer
Resta -> Substract in spanish
Restad -> Plural of substract in spanish (imperative).

In unix daemons finalize with a `d` so: we ask a bunch of unix processes running as a daemon to act as a REST API able to `restar`, so `restad` this numbers.

## Abstract

A simple REST API implemented with Python + Bottle to implement a basic calculator. Restad can run by itself as a single python process, multiprocess with gunicorn and opionally use Redis as backend when deployed in different containers / servers.

The development has been done following KISS (Keep it Simple Stupid) and UNIX philosophy (do one thing and do it well). As Redis already needed a container a Dockerfile and docker-compose.yml has been added as well.
º

## Assignment

Implement a **calculator** as a REST service, in any language you choose:
  add, sub, div, mult, sqrt, mean, std and reset.

The user must keep their last value, which is why the special `reset` operation exists.

Justify the design and implementation decisions taken under the SD (shared-state) paradigm.

**Delivery**: in AD (the campus delivery system), include the link to the (publicly accessible) repository containing the source code and the relevant descriptions.


## Design decisions

No versioning for the REST API, is too simple.

Normally I would go Flask or Django RESTframework. But will go even simpler with `bottle`.

JSON si really popular on REST APIS but is just a convetion, is not really needed, this API si not JSON, just plain strings. Numbers can be separated by commas to be lists.

To avoid a collisions used a hash based on timestamp + source ip + source port + some randomness. Hash function selected djb2, not becuase the best just becuse  DJB is awesome and always deserve credit.

The implementation has a dual way to operate with standard python shared memory or Redis. Locks also suport both backends.

Let's imagine an entity which is 'number list' so tryied to understand verbs from https://www.rfc-editor.org/rfc/rfc9110.html and use them properly on it.

## Idea

This is just for fun, to play with the REST concepts and a calculator.


This number list can be created (POST) with one or multiple númbers. You can GET the values as is or GET the desired operation result.

Also that values can be consilidated PUTing them into a single one.

Also more values can be added with the PATCH operation.

## Setup

Is needed uv and uvx.

    alias GET="uvx --from httpie http GET"
    alias POST="uvx --from httpie http POST"
    alias PUT="uvx --from httpie http PUT"
    alias PATCH="uvx --from httpie http PATCH"
    alias DELETE="uvx --from httpie http DELETE"

## Usage example

    uv run --with bottle==0.13.4 python app.py

## Server interface

Tried to follow HTTP Verb sematincs https://www.rfc-editor.org/rfc/rfc9110.html

Create a calculus with POST, you can send the first list of numbers in the payload:

    POST localhost:12345/calc --raw 3,4,5,6
    # Will return the calc-id as response and in the Location header

You can also create a calcules by PUTing all the content into the one you define.

    PUT localhost:12345/calc/my-calc --raw 3,4,5,6

Numbers can be added with PATCH

    PATCH localhost:12345/calc/my-calc --raw 7,8,9
    # <some-id> will contain the list 3,4,5,6,7,8,9

You can GET the content without an operation just responds the number list.

    GET localhost:12345/calc/my-calc
    # Will respond 3,4,5,6,7,8,9

You alse can can GET the result (without modifing the calcc) appending an operation

    GET localhost:12345/calc/my-calc/add
    # Will respond the meaning of life (42)

We can get the result as well as POSTing it into a consolidated result:

    POST localhost:12345/calc/my-calc/add
    # Will respond 42

    GET localhost:12345/calc/my-calc
    # Will respond 42

Finally we can DELETE the operation when no longer needed.

    DELETE localhost:12345/calc/my-calc
    # Will delete it

    GET localhost:12345/calc/my-calc
    # Will respond 404



## Observations

## AI usage

- gemini-3.1-pro (web): Translate <assignment title> to English
- gemini-3.1-pro (web): Many lookups of information about python libraries
- gemini-3.1-pro (web): Implement djb2 hash function
- MiniMax-M3.1-flash (opencode): Develop restad-client, restad-test, restad-bench & restadapi.py
- MiMo-2.6-flash (opencode): Can you check spell and grammar of README.md. Suggest the minimal changes keeping the style.
- MiMo-2.6-flash (opencode): Do the same f

