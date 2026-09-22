"""Evidence collectors.

Every collector returns the same Silver-layer inventory shape, so the scoring
engine never knows whether the evidence came from a live tenant or a fixture:

```python
{
    "tenant": {...},
    "workspaces": [...],
    "semantic_models": [...],
    "reports": [...],
    "data_agents": [...],
    "collection_errors": [...],
}
```

All collectors are strictly read-only.
"""

from fabric_iq.collectors.base import Collector, CollectionResult
from fabric_iq.collectors.offline import OfflineCollector
from fabric_iq.collectors.fabric_api import FabricApiCollector, FabricApiConfig, FabricHttpTransport

__all__ = [
    "Collector",
    "CollectionResult",
    "OfflineCollector",
    "FabricApiCollector",
    "FabricApiConfig",
    "FabricHttpTransport",
]
