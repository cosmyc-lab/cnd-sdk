"""Regenerate fixtures/hashes.json — the CND -> expected-hash vectors.

Run after any deliberate change to the hashable field subset or the
canonicalisation. The vectors are a conformance artifact (docs/adr/0016,
docs/adr/0020): an implementation in another language proves it computes
the same bytes by reproducing them.
"""

import json
from pathlib import Path

from cnd import Cnd, content_hash, node_hash

FIXTURES = Path(__file__).parent.parent / "fixtures"

vectors = {}
for path in sorted(FIXTURES.glob("*.cnd")):
    cnd = Cnd.model_validate_json(path.read_text())
    vectors[path.name] = {
        "content_hash": content_hash(cnd),
        "node_hashes": [node_hash(v.node) for v in cnd.iter()],
    }

(FIXTURES / "hashes.json").write_text(json.dumps(vectors, indent=2) + "\n")
print(f"wrote {len(vectors)} vectors")
