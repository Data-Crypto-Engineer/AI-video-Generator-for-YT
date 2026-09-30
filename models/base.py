import json
from typing import Any, Dict

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

    def Field(default=None, default_factory=None, **kwargs):
        if default_factory is not None:
            return default_factory()
        if default is ...:
            return None
        return default

    class BaseModel:
        def __init__(self, **data):
            # Fill defaults from class definitions first
            for k, v in self.__class__.__dict__.items():
                if not k.startswith("_") and not callable(v):
                    # deepcopy or instantiate if it was a default factory result
                    if isinstance(v, list):
                        setattr(self, k, list(v))
                    elif isinstance(v, dict):
                        setattr(self, k, dict(v))
                    elif v is ...:
                        setattr(self, k, None)
                    else:
                        setattr(self, k, v)

            # Override with passed data
            for k, v in data.items():
                setattr(self, k, v)

        def model_dump(self) -> Dict[str, Any]:
            res = {}
            for k, v in self.__dict__.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, BaseModel):
                    res[k] = v.model_dump()
                elif isinstance(v, list):
                    res[k] = [item.model_dump() if isinstance(item, BaseModel) else (item.value if hasattr(item, "value") else item) for item in v]
                elif hasattr(v, "value"):
                    res[k] = v.value
                elif v is ...:
                    res[k] = None
                else:
                    res[k] = v
            return res

        def dict(self) -> Dict[str, Any]:
            return self.model_dump()
