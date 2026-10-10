"""Commercial-owned ORM models (persistence contract remains in Core).

These tables were created by historical Core Alembic revisions. **New** vendor
DDL must land in ``canary-commercial`` ``module/migrations/versions/`` via
``commercial_module_migrate``, not in ``backend/alembic/versions``.

Imported by ``app.models`` and by Alembic so metadata stays complete.
"""

from __future__ import annotations

from app.models.casera import (  # noqa: F401
    CaseraCaseLink,
    CaseraIntegrationSettings,
    CaseraOrder,
    CaseraOrderProduct,
    CaseraWebhookEvent,
)
from app.models.hmlr import (  # noqa: F401
    HmlrCaseLink,
    HmlrIntegrationSettings,
    HmlrOrder,
)
from app.models.commercial_funds import CommercialFundsSettings  # noqa: F401
from app.models.search_integration import SearchIntegrationSettings  # noqa: F401
from app.models.signing import (  # noqa: F401
    DocusignDocumentTier,
    DocusignIntegrationSettings,
    DocusignRecipientStatus,
    DocusignSignatureLevel,
    DocusignSigningRecipient,
    DocusignSigningRequest,
    DocusignSigningStatus,
)
