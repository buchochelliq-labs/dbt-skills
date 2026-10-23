"""Explicit online preparation for the offline pipeline probe; no model weights.

Usage: python prestage_tokenizer.py /tmp/dbt-spike-hf-cache
Refuse source drift against the recorded experiment. This is not product setup.
"""
import hashlib
import json
from pathlib import Path
import sys
from huggingface_hub import hf_hub_download

records=json.loads((Path(__file__).parent/'results/tokenizer-artifacts.json').read_text())
for record in records:
    path=Path(hf_hub_download(record['repo'],record['filename'],token=False,
                             cache_dir=str(Path(sys.argv[1])/'hub')))
    if path.parent.name!=record['revision'] or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
        raise RuntimeError('Upstream tokenizer changed; review manifest before repeating the experiment')
    print(record['filename'],path.stat().st_size)
