from __future__ import annotations

import ast
import dataclasses
import datetime
import pathlib
import re
import sys
import unittest

from fabric_iq.surfaces import (
    CONSUMPTION_SURFACES,
    DATA_AGENT_CONCEPT_SOURCE,
    DATA_AGENT_TENANT_SETTINGS_SOURCE,
    ConsumptionSurface,
    Prerequisite,
)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SURFACES_PATH = REPO_ROOT / "fabric_iq" / "surfaces.py"
EXPECTED_KEYS = {
    "m365_copilot_chat",
    "m365_copilot_cowork",
    "power_bi_agent_m365",
    "fabric_data_agent_in_fabric",
    "fabric_data_agent_m365",
    "fabric_data_agent_external",
    "ontology",
    "operations_agent",
}
ALLOWED_KINDS = {
    "licence",
    "tenant_setting",
    "capacity",
    "region",
    "publication",
    "billing",
    "permission",
    "limitation",
}
#: Documented statuses as read on the registry's read date. Asserted per key so a
#: single GA -> preview flip (the Sprint 8.1 preceptor mutation) turns red.
EXPECTED_STATUS = {
    "m365_copilot_chat": "GA",
    "m365_copilot_cowork": "GA",
    "fabric_data_agent_in_fabric": "GA",
    "power_bi_agent_m365": "preview",
    "fabric_data_agent_m365": "preview",
    "fabric_data_agent_external": "preview",
    "ontology": "preview",
    "operations_agent": "preview",
}
#: Normalized fragments that mean "data leaves the geography". Matched against
#: every Cowork prerequisite regardless of kind, because a contradiction filed as
#: a `limitation` or `region` is still a contradiction.
CROSS_GEO_FRAGMENTS = (
    "crossgeo",
    "crossregion",
    "geographic",
    "geography",
    "intergeo",
    "multigeo",
    "outsidegeo",
)


def normalize(text: str) -> str:
    """Casefold and drop hyphens, spaces and underscores; unify Microsoft 365.

    "cross geo", "Cross-Geo" and "cross_geo" all become "crossgeo", so a
    spelling variant cannot slip past a substring check.
    """
    folded = re.sub(r"[\s\-_\u2010-\u2015]+", "", text.casefold())
    return folded.replace("microsoft365", "m365")


def surface_by_key(
    surfaces: tuple[ConsumptionSurface, ...], key: str
) -> ConsumptionSurface | None:
    return next((surface for surface in surfaces if surface.key == key), None)


def replace_surface(
    surfaces: tuple[ConsumptionSurface, ...], key: str, **changes: object
) -> tuple[ConsumptionSurface, ...]:
    """A copy of ``surfaces`` with one surface replaced in memory."""
    assert surface_by_key(surfaces, key) is not None, f"mutation anchor {key!r} is gone"
    return tuple(
        dataclasses.replace(surface, **changes) if surface.key == key else surface
        for surface in surfaces
    )


def registry_violations(surfaces: tuple[ConsumptionSurface, ...]) -> list[str]:
    """Every documented-fact invariant the registry must satisfy.

    Called on the real registry (must return ``[]``) and on in-memory mutated
    copies (each must return at least one violation). ``fabric_iq/surfaces.py``
    is never edited by this suite.
    """
    problems: list[str] = []

    # 1. Documented statuses, per key.
    actual = {surface.key: surface.status for surface in surfaces}
    for key, status in EXPECTED_STATUS.items():
        if actual.get(key) != status:
            problems.append(f"{key}: status {actual.get(key)!r}, documented {status!r}")

    # 2. Cowork documents no cross-geo requirement -- in any kind, any spelling.
    cowork = surface_by_key(surfaces, "m365_copilot_cowork")
    if cowork is None:
        problems.append("m365_copilot_cowork: missing")
    else:
        for prerequisite in cowork.prerequisites:
            text = normalize(prerequisite.statement)
            hits = [fragment for fragment in CROSS_GEO_FRAGMENTS if fragment in text]
            if hits:
                problems.append(
                    f"m365_copilot_cowork: {prerequisite.kind} prerequisite asserts a "
                    f"cross-geo condition ({', '.join(hits)}): {prerequisite.statement!r}"
                )

        # 5. Cowork permission (Read on report and semantic model) and billing.
        permissions = [
            normalize(p.statement) for p in cowork.prerequisites if p.kind == "permission"
        ]
        if not any(
            "read" in text and "report" in text and "semanticmodel" in text
            for text in permissions
        ):
            problems.append(
                "m365_copilot_cowork: no permission prerequisite requiring Read on the "
                "report and its semantic model"
            )
        billing = [
            normalize(p.statement) for p in cowork.prerequisites if p.kind == "billing"
        ]
        if not any("usagebased" in text for text in billing):
            problems.append("m365_copilot_cowork: no usage-based billing prerequisite")

    # 3. In-Fabric data agent: cross-geo processing AND storing, sourced.
    agent = surface_by_key(surfaces, "fabric_data_agent_in_fabric")
    if agent is None:
        problems.append("fabric_data_agent_in_fabric: missing")
    else:
        cross_geo = [
            p
            for p in agent.prerequisites
            if p.kind == "tenant_setting" and "crossgeo" in normalize(p.statement)
        ]
        texts = [normalize(p.statement) for p in cross_geo]
        for word in ("processing", "storing"):
            if not any(word in text for text in texts):
                problems.append(
                    f"fabric_data_agent_in_fabric: cross-geo tenant setting lacks {word}"
                )
        if any(p.source != DATA_AGENT_TENANT_SETTINGS_SOURCE for p in cross_geo):
            problems.append(
                "fabric_data_agent_in_fabric: cross-geo setting not sourced from the "
                "data-agent tenant-settings page"
            )
        if not any(
            p.kind == "capacity" and p.source == DATA_AGENT_CONCEPT_SOURCE
            for p in agent.prerequisites
        ):
            problems.append("fabric_data_agent_in_fabric: no sourced capacity prerequisite")

    # 4. Copilot Chat carries the three documented tenant settings.
    chat = surface_by_key(surfaces, "m365_copilot_chat")
    if chat is None:
        problems.append("m365_copilot_chat: missing")
    else:
        settings = [
            normalize(p.statement) for p in chat.prerequisites if p.kind == "tenant_setting"
        ]
        required = {
            "Fabric data available in Microsoft 365 Copilot": ("fabricdataavailableinm365copilot",),
            "Share Fabric data with your Microsoft 365 services": (
                "sharefabricdatawithyourm365services",
            ),
            "Azure OpenAI cross-geo processing": ("azureopenai", "crossgeoprocessing"),
        }
        for label, fragments in required.items():
            if not any(all(f in text for f in fragments) for text in settings):
                problems.append(f"m365_copilot_chat: missing tenant setting {label!r}")

    return problems


class ConsumptionSurfaceRegistryTests(unittest.TestCase):
    def assert_sources_valid(self, surfaces: tuple[ConsumptionSurface, ...]) -> None:
        for surface in surfaces:
            for prerequisite in surface.prerequisites:
                self.assertTrue(
                    prerequisite.source.startswith("https://learn.microsoft.com/"),
                    f"{surface.key}: invalid source {prerequisite.source!r}",
                )
                datetime.date.fromisoformat(prerequisite.read_on)

    def assert_no_cowork_cross_geo(
        self, surfaces: tuple[ConsumptionSurface, ...]
    ) -> None:
        cowork = surface_by_key(surfaces, "m365_copilot_cowork")
        self.assertIsNotNone(cowork)
        for prerequisite in cowork.prerequisites:
            text = normalize(prerequisite.statement)
            for fragment in CROSS_GEO_FRAGMENTS:
                self.assertNotIn(
                    fragment, text, f"{prerequisite.kind}: {prerequisite.statement!r}"
                )

    def test_registry_is_a_non_empty_tuple_with_unique_keys(self) -> None:
        self.assertIsInstance(CONSUMPTION_SURFACES, tuple)
        self.assertTrue(CONSUMPTION_SURFACES)
        keys = [surface.key for surface in CONSUMPTION_SURFACES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), EXPECTED_KEYS)
        self.assertTrue(ConsumptionSurface.__dataclass_params__.frozen)
        self.assertTrue(Prerequisite.__dataclass_params__.frozen)
        for surface in CONSUMPTION_SURFACES:
            self.assertIn(surface.status, {"GA", "preview"})
            self.assertIsInstance(surface.grounds_on, tuple)
            self.assertIsInstance(surface.prerequisites, tuple)
            for prerequisite in surface.prerequisites:
                self.assertIn(prerequisite.kind, ALLOWED_KINDS)

    def test_prerequisite_sources_and_read_dates_are_valid(self) -> None:
        self.assert_sources_valid(CONSUMPTION_SURFACES)

    def test_review_dates_follow_reads_by_no_more_than_ninety_days(self) -> None:
        for surface in CONSUMPTION_SURFACES:
            review_by = datetime.date.fromisoformat(surface.review_by)
            self.assertTrue(surface.prerequisites, f"{surface.key}: no sourced facts")
            for prerequisite in surface.prerequisites:
                read_on = datetime.date.fromisoformat(prerequisite.read_on)
                delta = review_by - read_on
                self.assertGreater(delta.days, 0, surface.key)
                self.assertLessEqual(delta.days, 90, surface.key)

    def test_cowork_has_no_cross_geo_tenant_setting(self) -> None:
        self.assert_no_cowork_cross_geo(CONSUMPTION_SURFACES)

    def test_in_fabric_data_agent_is_ga_with_capacity_and_cross_geo(self) -> None:
        agent = next(
            surface
            for surface in CONSUMPTION_SURFACES
            if surface.key == "fabric_data_agent_in_fabric"
        )
        self.assertEqual(agent.status, "GA")
        capacity = [
            prerequisite
            for prerequisite in agent.prerequisites
            if prerequisite.kind == "capacity"
        ]
        self.assertTrue(capacity)
        self.assertTrue(
            any(
                prerequisite.source == DATA_AGENT_CONCEPT_SOURCE
                for prerequisite in capacity
            )
        )
        cross_geo = [
            prerequisite
            for prerequisite in agent.prerequisites
            if prerequisite.kind == "tenant_setting"
            and "crossgeo" in normalize(prerequisite.statement)
        ]
        self.assertTrue(cross_geo)
        joined = " ".join(normalize(p.statement) for p in cross_geo)
        self.assertIn("processing", joined)
        self.assertIn("storing", joined)
        self.assertTrue(
            all(
                prerequisite.source == DATA_AGENT_TENANT_SETTINGS_SOURCE
                for prerequisite in cross_geo
            )
        )

    def test_registry_module_uses_only_the_standard_library(self) -> None:
        tree = ast.parse(SURFACES_PATH.read_text(encoding="utf-8"))
        imported_roots = {
            alias.name.partition(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.partition(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertLessEqual(imported_roots, sys.stdlib_module_names)

    def test_registry_is_decoupled_from_rules_scoring_and_collectors(self) -> None:
        tree = ast.parse(SURFACES_PATH.read_text(encoding="utf-8"))
        imports = self._imports(tree)
        forbidden = (
            "fabric_iq.rules",
            "fabric_iq.scoring",
            "fabric_iq.collectors",
        )
        self.assertFalse(
            any(
                name == prefix or name.startswith(f"{prefix}.")
                for name in imports
                for prefix in forbidden
            )
        )

        consumers = [REPO_ROOT / "fabric_iq" / "scoring.py"]
        consumers.extend((REPO_ROOT / "fabric_iq" / "rules").rglob("*.py"))
        consumers.extend((REPO_ROOT / "fabric_iq" / "collectors").rglob("*.py"))
        for path in consumers:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            self.assertFalse(self._imports_surface_registry(tree), str(path))

    def test_mutated_row_fails_source_and_contradiction_checks(self) -> None:
        cowork_index = next(
            index
            for index, surface in enumerate(CONSUMPTION_SURFACES)
            if surface.key == "m365_copilot_cowork"
        )
        cowork = CONSUMPTION_SURFACES[cowork_index]
        contradiction = Prerequisite(
            "tenant_setting",
            "Azure OpenAI cross-geo processing must be enabled.",
            "http://example.invalid/source",
            "2026-09-27",
        )
        mutated_cowork = dataclasses.replace(
            cowork, prerequisites=cowork.prerequisites + (contradiction,)
        )
        mutated = (
            CONSUMPTION_SURFACES[:cowork_index]
            + (mutated_cowork,)
            + CONSUMPTION_SURFACES[cowork_index + 1 :]
        )

        with self.assertRaises(AssertionError):
            self.assert_sources_valid(mutated)
        with self.assertRaises(AssertionError):
            self.assert_no_cowork_cross_geo(mutated)

    def test_documented_statuses_hold_per_surface(self) -> None:
        self.assertEqual(set(EXPECTED_STATUS), EXPECTED_KEYS)
        actual = {surface.key: surface.status for surface in CONSUMPTION_SURFACES}
        self.assertEqual(actual, EXPECTED_STATUS)

    def test_real_registry_has_no_documented_fact_violations(self) -> None:
        self.assertEqual(registry_violations(CONSUMPTION_SURFACES), [])

    def test_copilot_chat_carries_the_three_documented_tenant_settings(self) -> None:
        chat = surface_by_key(CONSUMPTION_SURFACES, "m365_copilot_chat")
        settings = [
            normalize(p.statement) for p in chat.prerequisites if p.kind == "tenant_setting"
        ]
        for fragments in (
            ("fabricdataavailableinm365copilot",),
            ("sharefabricdatawithyourm365services",),
            ("azureopenai", "crossgeoprocessing"),
        ):
            with self.subTest(fragments=fragments):
                self.assertTrue(
                    any(all(f in text for f in fragments) for text in settings), settings
                )

    def test_cowork_requires_read_permission_and_usage_based_billing(self) -> None:
        cowork = surface_by_key(CONSUMPTION_SURFACES, "m365_copilot_cowork")
        permission = [
            normalize(p.statement) for p in cowork.prerequisites if p.kind == "permission"
        ]
        self.assertTrue(
            any("read" in t and "report" in t and "semanticmodel" in t for t in permission)
        )
        billing = [
            normalize(p.statement) for p in cowork.prerequisites if p.kind == "billing"
        ]
        self.assertTrue(any("usagebased" in t for t in billing))

    def test_normalize_folds_spelling_variants(self) -> None:
        for variant in ("cross geo", "Cross-Geo", "cross_geo", "CROSS \u2011 GEO"):
            with self.subTest(variant=variant):
                self.assertEqual(normalize(variant), "crossgeo")
        self.assertEqual(normalize("Microsoft 365"), "m365")

    def test_each_preceptor_mutation_is_caught(self) -> None:
        """Every in-memory mutation @change-preceptor showed passing now fails.

        Each case names the violation fragment it must produce, so a mutation
        caught for an unrelated reason does not count as caught.
        """
        real = CONSUMPTION_SURFACES
        cowork = surface_by_key(real, "m365_copilot_cowork")
        chat = surface_by_key(real, "m365_copilot_chat")
        agent = surface_by_key(real, "fabric_data_agent_in_fabric")

        def with_cowork_extra(kind: str, statement: str):
            extra = Prerequisite(kind, statement, cowork.prerequisites[0].source, "2026-09-27")
            return replace_surface(
                real, cowork.key, prerequisites=cowork.prerequisites + (extra,)
            )

        def without(surface, predicate):
            kept = tuple(p for p in surface.prerequisites if not predicate(p))
            self.assertNotEqual(len(kept), len(surface.prerequisites), "anchor gone")
            return replace_surface(real, surface.key, prerequisites=kept)

        mutations = {
            # 1. status flips
            "cowork GA -> preview": (
                replace_surface(real, cowork.key, status="preview"),
                "m365_copilot_cowork: status 'preview'",
            ),
            "chat GA -> preview": (
                replace_surface(real, chat.key, status="preview"),
                "m365_copilot_chat: status",
            ),
            "in-fabric agent GA -> preview": (
                replace_surface(real, agent.key, status="preview"),
                "fabric_data_agent_in_fabric: status",
            ),
            "ontology preview -> GA": (
                replace_surface(real, "ontology", status="GA"),
                "ontology: status",
            ),
            # 2. cross-geo spelling variants, any kind, validly sourced
            "cowork 'cross geo processing' tenant_setting": (
                with_cowork_extra(
                    "tenant_setting", "cross geo processing must be enabled"
                ),
                "cross-geo condition",
            ),
            "cowork 'Cross_Geo' limitation": (
                with_cowork_extra("limitation", "Requires Cross_Geo data movement."),
                "cross-geo condition",
            ),
            "cowork cross-region region": (
                with_cowork_extra("region", "Cross region processing is required."),
                "cross-geo condition",
            ),
            "cowork geographic billing": (
                with_cowork_extra(
                    "billing", "Data may be processed outside your geographic boundary."
                ),
                "cross-geo condition",
            ),
            # 3. in-Fabric agent loses storing
            "in-fabric agent loses storing": (
                replace_surface(
                    real,
                    agent.key,
                    prerequisites=tuple(
                        dataclasses.replace(
                            p, statement="Cross-geo processing for AI must be enabled."
                        )
                        if p.kind == "tenant_setting"
                        else p
                        for p in agent.prerequisites
                    ),
                ),
                "lacks storing",
            ),
            # 4. chat loses each documented setting
            "chat loses Share Fabric data": (
                without(chat, lambda p: "sharefabricdata" in normalize(p.statement)),
                "'Share Fabric data with your Microsoft 365 services'",
            ),
            "chat loses Fabric data available": (
                without(chat, lambda p: "fabricdataavailable" in normalize(p.statement)),
                "'Fabric data available in Microsoft 365 Copilot'",
            ),
            "chat loses Azure OpenAI cross-geo": (
                without(chat, lambda p: "azureopenai" in normalize(p.statement)),
                "'Azure OpenAI cross-geo processing'",
            ),
            # 5. cowork loses permission / billing
            "cowork loses permission": (
                without(cowork, lambda p: p.kind == "permission"),
                "no permission prerequisite",
            ),
            "cowork permission loses semantic model": (
                replace_surface(
                    real,
                    cowork.key,
                    prerequisites=tuple(
                        dataclasses.replace(
                            p, statement="Users need Read permission on the report."
                        )
                        if p.kind == "permission"
                        else p
                        for p in cowork.prerequisites
                    ),
                ),
                "no permission prerequisite",
            ),
            "cowork loses usage-based billing": (
                without(cowork, lambda p: p.kind == "billing"),
                "no usage-based billing",
            ),
        }
        self.assertEqual(registry_violations(real), [], "real registry must be green")
        for label, (mutated, expected) in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(mutated, real, "mutation changed nothing")
                violations = registry_violations(mutated)
                self.assertTrue(
                    any(expected in v for v in violations),
                    f"{label}: expected {expected!r} in {violations}",
                )
        self.assertEqual(registry_violations(CONSUMPTION_SURFACES), [], "no leak")

    def test_cross_geo_variant_fails_the_assertion_helper_too(self) -> None:
        cowork = surface_by_key(CONSUMPTION_SURFACES, "m365_copilot_cowork")
        for kind in ("tenant_setting", "limitation", "region"):
            with self.subTest(kind=kind):
                extra = Prerequisite(
                    kind,
                    "cross geo processing must be enabled",
                    cowork.prerequisites[0].source,
                    "2026-09-27",
                )
                mutated = replace_surface(
                    CONSUMPTION_SURFACES,
                    cowork.key,
                    prerequisites=cowork.prerequisites + (extra,),
                )
                self.assert_sources_valid(mutated)  # validly sourced...
                with self.assertRaises(AssertionError):  # ...and still caught
                    self.assert_no_cowork_cross_geo(mutated)

    @staticmethod
    def _imports(tree: ast.AST) -> set[str]:
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        return imports

    @staticmethod
    def _imports_surface_registry(tree: ast.AST) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "fabric_iq.surfaces"
                or alias.name.startswith("fabric_iq.surfaces.")
                for alias in node.names
            ):
                return True
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module in {"fabric_iq.surfaces", "surfaces"}:
                return True
            if module == "fabric_iq" and any(
                alias.name == "surfaces" for alias in node.names
            ):
                return True
            if node.level and not module and any(
                alias.name == "surfaces" for alias in node.names
            ):
                return True
        return False


if __name__ == "__main__":
    unittest.main()

