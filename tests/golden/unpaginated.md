---
title: "Protocol notes"
lang: "en"
cnd_version: "0.3.0"
built_at: "2026-07-22T09:30:00+00:00"
---

# Handshake

The client opens with a version token, as shown in the listing below.
[lst-open] [^fn-token]

```text
OPEN v1

```

*Opening frame*

## Footnotes

[^fn-token]: The version token is opaque to intermediaries.

## Bibliography

- **rivest1978** — Rivest, R.. (1978). On data banks and privacy homomorphisms
