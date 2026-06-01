"""REST routers for the Memory Rhythm demo.

Each module exposes an ``APIRouter`` mounted under the ``/api`` prefix by
``app.main``. Routers are thin and delegate to ``app.store`` and the service
layer per the shared contract (see CONTRACT.md §4).
"""

from app.routers import autobiography, caregiver, community, patients, survey

__all__ = ["patients", "autobiography", "caregiver", "community", "survey"]
