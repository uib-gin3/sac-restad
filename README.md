# restad REST Daemon that knows how to "restar"

Rest -> Application Programming Interface y Representational State Transfer
Resta -> Substract in spanish
Restad -> Plural of substract in spanish (imperative). If we consider the aplication restad a group of procesces able to substract.
In unix daemons finalize with a `d` so: restad is a REST API able to `restar` amoung others operations Daemon 

Please set of threads 'restad' this numbers.

## Abstract

## Assignment

Implement a **calculator** as a REST service, in any language you choose:
  add, sub, div, mult, sqrt, mean, std and reset.

The user must keep their last value, which is why the special `reset` operation exists.

Justify the design and implementation decisions taken under the SD (shared-state) paradigm.

**Delivery**: in AD (the campus delivery system), include the link to the (publicly accessible) repository containing the source code and the relevant descriptions.

## Idea

This is just for fun, to play with the REST concepts and a calculator.

Let's imagine an entity which is 'number list'.

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

    POST localhost:12345 12.2,4,10,5

    GET 

## Design decisions

No versioning too simple to version

Normally I would go Flask. The code would be really clean. But lets do it manually stdlib way

JSON si really popular on REST APIS but is just a convetion, is not really needed.

To avoid a collision of requests taken the timestamp + source ip + source port and hash it. Hash function selected djb2, not becuase the best just becus  DJB is awesome and always deserve credit.

Lock operation?

reset -> clear



## Observations

## AI usage

gemini 3.1 pro web com un cercador
gemini implementació de djb2

