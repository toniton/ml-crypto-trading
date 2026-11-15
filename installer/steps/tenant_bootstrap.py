"""Cloud tenant bootstrap step for multi-tenant deployments."""

import os
import re

from installer.context import InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console


class TenantBootstrapStep(BaseStep):
    """Validates and populates TENANT_USER_ID for cloud container instances."""

    TENANT_SLUG_PATTERN = re.compile(r"^(default|usr-[a-z0-9]{4,32})$")

    @property
    def name(self) -> str:
        return "Multi-Tenant Context Bootstrap"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)
        env_tenant = os.getenv("TENANT_USER_ID", "").strip().lower()
        resolved = env_tenant or context.app.tenant_user_id.strip().lower() or "default"

        if not self.TENANT_SLUG_PATTERN.match(resolved):
            console.error(f"Invalid TENANT_USER_ID '{resolved}'. Expected 'default' or 'usr-<id>'.")
            return False

        context.app.tenant_user_id = resolved
        console.success(f"Configured tenant context: {resolved}")
        return True
