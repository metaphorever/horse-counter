"""
famous.py - Notable / famous horse recognition.

Data is loaded from data/famous_horses.json (built by build_famous.py).
Keys are normalized horse names (same normalization as matcher.py).
"""

import json
import os
from typing import List, Optional


class FamousHorses:
    def __init__(self, path: str):
        self.horses: dict = {}
        self.loaded = False
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    self.horses = json.load(f)
                self.loaded = True
                print(f"Loaded {len(self.horses)} famous horses")
            except Exception as e:
                print(f"Famous horses load error: {e}")

    def lookup(self, normalized_name: str) -> Optional[dict]:
        return self.horses.get(normalized_name)

    def tags_for(self, normalized_name: str) -> List[str]:
        info = self.horses.get(normalized_name)
        return list(info['tags']) if info else []
