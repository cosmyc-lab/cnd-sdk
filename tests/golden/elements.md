---
title: "Elements of format 0.5"
lang: "en"
status: "Approved"
version: "1.2"
extra:
  "client": "ACME"
  "reference": "PRJ-042"
cnd_version: "0.5.0"
built_at: "2026-10-13T00:00:00+00:00"
---

# Section 1 Elements of format 0.5

Pressure **rose** 10<sup>3</sup> times, see Theorem 1 and the note, after Knuth: $E = m c^2$ holds.
[thm-main] [^fn-detail] @knuth1984

> [!WARNING]
> **Careful**
>
> Never edit a CND in place.

1. [x] Compile the source
   - with fonts
2. [ ] Validate the output

***Mark***
: A standoff span with a kind.

  Marks of different kinds may overlap.

| Station | hPa |
| --- | --- |
| Brest | 1013 |

![Before](a.png)

![After](b.png)

Energy and mass are equivalent.

*Theorem 1: Mass–energy equivalence*

States that energy equals mass times the speed of light squared.

> First paragraph of the quote.
>
> Second paragraph.
>
> — *A. Einstein*

main.py
```python
print('hi')

```

a^2 + b^2 = c^2

## Footnotes

[^fn-detail]: Details live here.

    A second paragraph, with `code`.

## Bibliography

- **knuth1984** — Knuth, D. *The TeXbook*. Addison-Wesley, 1984.
