"""The base every CND model shares: a closed object.

A key the format does not define is a **rejection**, never a silent drop.
Dropping it let a producer's typo (``captoin`` for ``caption``) or a
field written for another format version vanish on parse while the CND
still validated, so the mistake surfaced nowhere. The generated schema
says the same with ``additionalProperties: false`` on every object.

Forward compatibility does not need tolerance here: a CND declares its
``cnd_version``, and a reader refuses any version but its own before it
looks at the shape (spec §9, §11). The free-form bags
(``state_metadata``, ``BibEntry.fields``, ``doc.extra``) are dict-typed
fields, so they still hold any key.
"""

from pydantic import BaseModel, ConfigDict


class ClosedModel(BaseModel):
    """A CND object: its own fields and nothing else."""

    model_config = ConfigDict(extra="forbid")
