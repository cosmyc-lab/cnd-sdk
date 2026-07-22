"""Regenerate fixtures/traversal.json — the CND -> expected id sequence vectors.

Walk order is normative prose (spec §8) and per-language by construction
(docs/adr/0019), so two implementations can disagree invisibly: nothing
in the file records the order they chose. These vectors are what make
that disagreement detectable.
"""

import json
from pathlib import Path

from cnd import Cnd

FIXTURES = Path(__file__).parent.parent / "fixtures"

vectors = {}
for path in sorted(FIXTURES.glob("*.cnd")):
    cnd = Cnd.model_validate_json(path.read_text())
    vectors[path.name] = [
        {"id": str(v.node.id), "type": v.node.type, "depth": v.ctx.depth}
        for v in cnd.iter()
    ]

(FIXTURES / "traversal.json").write_text(json.dumps(vectors, indent=2) + "\n")
print(f"wrote {len(vectors)} vectors, {sum(len(v) for v in vectors.values())} nodes")
