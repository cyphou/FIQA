"""Shared helpers for the test suite.

Fixtures are synthetic. No customer, tenant or personal data is used anywhere
in this project.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_TENANT = os.path.join(REPO_ROOT, "examples", "sample_tenant")


def ready_model(**overrides):
    """A semantic model subject that satisfies every SEM rule."""
    subject = {
        "id": "sm-test",
        "name": "Test Model",
        "parent_id": "ws-test",
        "tables": [
            {"name": "Sales", "role": "fact", "description": "Invoiced sales at line grain.", "is_date_table": False},
            {"name": "Customer", "role": "dimension", "description": "Billed customer entity.", "is_date_table": False},
            {"name": "Date", "role": "dimension", "description": "Daily calendar with fiscal year.", "is_date_table": True},
        ],
        "columns": [
            {"name": "Order Date", "description": "Date the order was confirmed.", "data_type": "dateTime",
             "semantic_role": "date", "summarize_by": "none", "hidden": False},
            {"name": "Fiscal Year", "description": "Fiscal year label starting in July.", "data_type": "int64",
             "semantic_role": "year", "summarize_by": "none", "hidden": False},
        ],
        "measures": [
            {"name": "Total Sales", "description": "Net invoiced revenue excluding tax.",
             "expression": "SUM(Sales[Net])", "synonyms": ["Revenue"], "hidden": False},
            {"name": "Gross Margin", "description": "Net revenue minus standard cost.",
             "expression": "[Total Sales] - [Cost]", "synonyms": ["Margin"], "hidden": False},
        ],
        "relationships": [{"name": "Sales-Date", "invalid": False, "ambiguous": False}],
        "has_time_intelligence": True,
        "visible_object_count": 7,
        "ai_data_schema": {"selected_objects": 5, "missing_dependencies": []},
        "ai_instructions": "Sales domain. " + ("Route revenue questions to [Total Sales]. " * 12),
        "verified_answers": [{"question": f"Q{i}", "broken": False} for i in range(5)],
        "rls_required": True,
        "rls_roles": [{"name": "Region", "tested": True}],
        "hours_since_refresh": 4,
        "freshness_sla_hours": 24,
        "schema_retrieval_error": None,
    }
    subject.update(overrides)
    return subject


def ready_tenant(**overrides):
    """A tenant subject with no blocking finding."""
    subject = {
        "id": "tenant-test",
        "name": "Test Tenant",
        "fabric_enabled": True,
        "copilot_enabled": True,
        "agents_enabled": True,
        "copilot_security_groups": ["sg-pilot"],
        "capacities": [{"id": "c1", "name": "Prod", "sku": "F64", "state": "Active", "throttled": False}],
        "cross_geo_required": False,
        "cross_geo_approved": False,
        "scanner_enabled": True,
        "scanner_service_principal": "sp-readiness",
        "workspaces_total": 2,
        "workspaces_scanned": 2,
        "sensitivity_labels_enabled": True,
        "labelled_item_ratio": 0.95,
        "owners": {"platform": "a", "security": "b", "business": "c"},
        "audit_log_enabled": True,
        "copilot_capacity_designation_enabled": True,
        "purview_dlp_reviewed": True,
    }
    subject.update(overrides)
    return subject


def minimal_inventory(**overrides):
    """A structurally valid inventory with a single healthy tenant."""
    inventory = {
        "tenant": ready_tenant(),
        "workspaces": [],
        "semantic_models": [],
        "reports": [],
        "data_agents": [],
        "collection_errors": [],
    }
    inventory.update(overrides)
    return inventory
