"""The Skill is never load-bearing: the tool must be usable without it.

A human runs `assess.py`, reads a console block that ends with a path, and opens
that path. No agent Skill is loaded in that story, and none may be required for
it. Three properties hold that up, and each one regresses silently:

1. **The pointer resolves.** `fabric_iq.reporting.INTERPRETATION_GUIDE` is printed
   by every console run and every HTML report. If the document it names is renamed
   or deleted, the tool ships a dead path to every operator.
2. **The guide has an accountable owner.** A document that tells an operator how to
   act on a verdict is a promise; an unowned promise goes stale in silence, which is
   the failure class `scripts/check_agent_ownership.py` already gates.
3. **The operational knowledge lives in human documentation.** The concepts below
   once existed only in `.github/skills/**` and `.github/agents/**`. A model reads
   those; an operator does not. This module scans *only* human-facing files, so
   deleting the guide and leaving the Skill fails the gate instead of passing it.

Concepts are matched by *co-occurring facets inside one passage*, never by an exact
sentence: a reasonable rewording must still pass, while scattered keywords or a
deleted paragraph must not. `TestTheConceptGateDetectsRemoval` proves both ends of
that on synthetic text -- a gate that cannot fail is decoration.
"""

import os
import re
import shutil
import tempfile
import unittest
from collections import defaultdict

from fabric_iq.reporting import INTERPRETATION_GUIDE
from tests.helpers import REPO_ROOT

#: Files a human reads. Everything a *model* reads lives under `.github/` and is
#: deliberately absent: the corpus is the point of the gate, not an accident.
HUMAN_DOC_ROOTS = ("README.md", "docs")
AI_FACING_PREFIXES = (".github/",)
SKILL_RELATIVE = ".github/skills/fabric-iq-readiness/SKILL.md"

#: Characters of flattened text within which every facet of a concept must appear.
#: Wide enough to span a heading plus its paragraph, narrow enough that unrelated
#: mentions in different sections cannot combine into a phantom explanation.
WINDOW = 800


class Concept:
    """One operational idea, expressed as facets that must occur together.

    Each facet is an alternation of the ways this project, or a reasonable editor
    rewriting it, would phrase that part of the idea. A concept counts as present
    only when every facet matches inside a single :data:`WINDOW` of one document.
    """

    def __init__(self, summary: str, *facets: str):
        self.summary = summary
        self.facets = facets


CONCEPTS: dict[str, Concept] = {
    "refusal_beats_answering_everything": Concept(
        "an agent that never refuses is more dangerous than one that answers less",
        r"refus\w*|declin\w*|(?:say|says|saying) no|out[- ]of[- ]scope",
        r"danger\w*|risk\w*|harm\w*|unsafe|worse|destroy\w+ trust|erod\w+ trust"
        r"|fabricat\w*|hallucinat\w*|mislead\w*",
        r"answers? (?:less|fewer|everything|anything)|always answers|never refuses"
        r"|answer\w* more|over[- ]answer\w*|answers every",
    ),
    "not_evaluated_is_fixed_by_collecting": Concept(
        "NOT_EVALUATED is fixed by collecting more evidence, never by re-scoring",
        r"not[_ ]?evaluated",
        r"collect\w*|gather\w*|more evidence|observ\w*|improve collection",
        r"re-?scor\w*|scor\w+ the same evidence|scor\w+ (?:it|them) again"
        r"|re-?run until",
    ),
    "endorsement_is_self_attestation": Concept(
        '"Approved for Copilot" is self-attestation, not proof',
        r"approved for copilot|endors\w*|certif\w*|badge",
        r"self-?attest\w*|author'?s? (?:own )?(?:claim|intent|attestation|word)"
        r"|set by the (?:content )?author|declared by the author"
        r"|(?:states?|expresses) intent",
        r"not (?:a |objective )?proof|never proof|is not evidence|not evidence of"
        r"|never moves? a score|cannot move a score|no rule .{0,60}reads",
    ),
    "over_broad_ai_data_schema_is_a_problem": Concept(
        "an over-broad AI data schema is a problem rather than generosity",
        r"(?:ai )?data schema",
        r"over-?broad|too broad|\bbroad\w*|everything|every (?:object|table|column|item)"
        r"|all (?:objects|tables|of them)|wide\w*",
        r"problem|not generosity|lowers precision|worse|degrad\w*|fails|noise"
        r"|hurts|dilut\w*|scoping",
    ),
    "blocking_findings_are_read_first": Concept(
        "blocking findings are read before anything else",
        r"blocking (?:finding|failure|rule)s?",
        r"\bfirst\b|come first|before (?:anything|everything|the|you)|start with"
        r"|ahead of",
        r"\bread\w*|\btriage\w*|in that order|order you should",
    ),
}


def flatten(text: str) -> str:
    """Runs of whitespace collapsed, so a claim wrapped over lines still reads."""
    return re.sub(r"\s+", " ", text)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def human_docs(root: str = REPO_ROOT) -> dict[str, str]:
    """Human-facing markdown as ``relative path -> flattened text``.

    Nothing under `.github/` is collected. That exclusion is the gate: a concept
    that survives only in a Skill or an agent file is, for an operator, gone.
    """
    docs: dict[str, str] = {}
    for relative in HUMAN_DOC_ROOTS:
        path = os.path.join(root, relative.replace("/", os.sep))
        if os.path.isfile(path):
            docs[relative] = flatten(_read(path))
        elif os.path.isdir(path):
            for dirpath, _dirnames, filenames in os.walk(path):
                for filename in sorted(filenames):
                    if not filename.endswith(".md"):
                        continue
                    absolute = os.path.join(dirpath, filename)
                    key = os.path.relpath(absolute, root).replace(os.sep, "/")
                    docs[key] = flatten(_read(absolute))
    return docs


def covering_passage(text: str, concept: Concept, window: int = WINDOW):
    """The shortest passage carrying every facet, or ``None`` if there is none."""
    hits: list[tuple[int, int]] = []
    for index, facet in enumerate(concept.facets):
        positions = [m.start() for m in re.finditer(facet, text, re.IGNORECASE)]
        if not positions:
            return None
        hits.extend((position, index) for position in positions)
    hits.sort()

    counts: dict[int, int] = defaultdict(int)
    present = 0
    left = 0
    for position, index in hits:
        counts[index] += 1
        if counts[index] == 1:
            present += 1
        while present == len(concept.facets):
            start = hits[left][0]
            if position - start <= window:
                return text[start : position + 1]
            counts[hits[left][1]] -= 1
            if counts[hits[left][1]] == 0:
                present -= 1
            left += 1
    return None


def documents_carrying(concept: Concept, docs: dict[str, str], window: int = WINDOW):
    """Every document in which the concept is explained in one passage."""
    return sorted(
        path for path, text in docs.items()
        if covering_passage(text, concept, window) is not None
    )


def missing_concepts(docs: dict[str, str], window: int = WINDOW) -> list[str]:
    """Concept names no document in the corpus explains."""
    return sorted(
        name for name, concept in CONCEPTS.items()
        if not documents_carrying(concept, docs, window)
    )


class TestTheReportPointerResolves(unittest.TestCase):
    """Gate 1: no dangling pointer.

    The path is taken from the constant the renderers use, never retyped here.
    Duplicating the literal would let the test keep passing against a document the
    tool no longer names.
    """

    def guide_path(self) -> str:
        return os.path.join(REPO_ROOT, INTERPRETATION_GUIDE.replace("/", os.sep))

    def test_the_referenced_guide_exists(self):
        self.assertTrue(
            os.path.isfile(self.guide_path()),
            f"fabric_iq.reporting.INTERPRETATION_GUIDE names {INTERPRETATION_GUIDE}, "
            "which no longer exists: every console run and HTML report now prints a "
            "dead path. Restore the document or update the constant (@readme, "
            "@lakehouse), never only one",
        )

    def test_the_referenced_guide_is_not_a_stub(self):
        text = _read(self.guide_path())
        self.assertGreater(
            len(text.split()), 300,
            f"{INTERPRETATION_GUIDE} is too thin to be the guide the CLI promises",
        )
        self.assertTrue(text.lstrip().startswith("#"), "the guide has no title")

    def test_the_pointer_is_a_repo_relative_path(self):
        self.assertFalse(os.path.isabs(INTERPRETATION_GUIDE))
        self.assertNotIn("..", INTERPRETATION_GUIDE)
        self.assertNotIn("\\", INTERPRETATION_GUIDE)
        self.assertTrue(INTERPRETATION_GUIDE.endswith(".md"))

    def test_the_pointer_targets_human_documentation_not_a_skill(self):
        # Pointing an operator at `.github/skills/...` would make the Skill the
        # home of the guidance again, by a different route.
        for prefix in AI_FACING_PREFIXES:
            self.assertFalse(
                INTERPRETATION_GUIDE.startswith(prefix),
                f"the report points operators at AI-facing content: {INTERPRETATION_GUIDE}",
            )

    def test_the_guide_is_part_of_the_human_corpus(self):
        self.assertIn(INTERPRETATION_GUIDE, human_docs())

    def test_the_pointer_target_is_a_document_somebody_owns(self):
        from scripts.check_agent_ownership import REQUIRED_DOCS

        self.assertIn(
            INTERPRETATION_GUIDE, REQUIRED_DOCS,
            "the document the reports hardcode must carry a named accountable owner",
        )


class TestTheGuideHasAnAccountableOwner(unittest.TestCase):
    """Gate 2: the guide is claimed by exactly one agent, and it is @readme."""

    def test_required_docs_names_readme_as_the_accountable_owner(self):
        from scripts.check_agent_ownership import REQUIRED_DOCS

        self.assertEqual(REQUIRED_DOCS.get("docs/INTERPRETING_RESULTS.md"), "readme")

    def test_the_readme_agent_has_claimed_it(self):
        from scripts.check_agent_ownership import claims

        self.assertEqual(
            claims().get("docs/INTERPRETING_RESULTS.md"), ["readme"],
            "docs/INTERPRETING_RESULTS.md must be claimed exactly once, by @readme, "
            "in the 'Your Files (You Own These)' block of .github/agents/readme.agent.md",
        )

    def test_the_guide_passes_the_documentation_ownership_audit(self):
        from scripts.check_agent_ownership import audit_docs

        unclaimed, duplicated, misassigned = audit_docs()
        guide = "docs/INTERPRETING_RESULTS.md"
        self.assertNotIn(guide, unclaimed)
        self.assertNotIn(guide, duplicated)
        self.assertNotIn(guide, misassigned)

    def test_the_ownership_script_reports_no_missing_document(self):
        from scripts.check_agent_ownership import missing_docs

        self.assertEqual(missing_docs(), [])

    def test_the_ownership_script_fails_when_an_owned_document_disappears(self):
        # Proof that the entry is load-bearing: an owner for a file that is gone is
        # a stale promise, and the script -- not only the suite -- must say so.
        from scripts.check_agent_ownership import missing_docs

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            os.makedirs(os.path.join(root, "docs"))
            required = {"docs/INTERPRETING_RESULTS.md": "readme"}
            self.assertEqual(missing_docs(root, required), list(required))

            with open(
                os.path.join(root, "docs", "INTERPRETING_RESULTS.md"), "w",
                encoding="utf-8",
            ) as handle:
                handle.write("# Interpreting Results\n")
            self.assertEqual(missing_docs(root, required), [])

    def test_an_unclaimed_guide_is_reported_against_its_named_owner(self):
        # The checker, against a synthetic agent tree: @readme exists but has not
        # claimed the guide, so the audit must name it rather than stay silent.
        from scripts.check_agent_ownership import audit_docs

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            agents = os.path.join(root, ".github", "agents")
            os.makedirs(agents)
            os.makedirs(os.path.join(root, "docs"))
            with open(os.path.join(agents, "readme.agent.md"), "w", encoding="utf-8") as h:
                h.write("---\nname: readme\n---\n\n## Your Files\n\n- `README.md`\n\n## Constraints\n")
            required = {"docs/INTERPRETING_RESULTS.md": "readme"}

            unclaimed, duplicated, misassigned = audit_docs(agents, root, required)

            self.assertEqual(unclaimed, ["docs/INTERPRETING_RESULTS.md"])
            self.assertEqual(duplicated, {})
            self.assertEqual(misassigned, {})


class TestOperationalGuidanceLivesInHumanDocs(unittest.TestCase):
    """Gate 3: the Skill is not the sole home of the operational knowledge."""

    def setUp(self):
        self.docs = human_docs()

    def test_the_corpus_excludes_ai_facing_files(self):
        for path in self.docs:
            with self.subTest(path=path):
                self.assertFalse(path.startswith(AI_FACING_PREFIXES))
        self.assertNotIn(SKILL_RELATIVE, self.docs)

    def test_the_skill_still_exists_and_is_still_excluded(self):
        # The Skill is optional, not forbidden. This gate must pass or fail on the
        # human documentation alone, whatever the Skill happens to say today.
        self.assertTrue(
            os.path.isfile(os.path.join(REPO_ROOT, SKILL_RELATIVE.replace("/", os.sep)))
        )
        self.assertNotIn(SKILL_RELATIVE, self.docs)

    def test_every_concept_is_explained_in_human_documentation(self):
        for name, concept in CONCEPTS.items():
            with self.subTest(concept=name):
                self.assertTrue(
                    documents_carrying(concept, self.docs),
                    f"no human-facing document explains that {concept.summary}. "
                    "An operator who never loads the Skill cannot learn it, which "
                    "makes the Skill load-bearing. Put it back in docs/ or README.md",
                )

    def test_no_concept_depends_on_a_single_stray_sentence_elsewhere(self):
        # Each concept must be explained in a document that also explains at least
        # one other, i.e. there is a real guide, not five orphaned sentences.
        carriers = defaultdict(list)
        for name, concept in CONCEPTS.items():
            for path in documents_carrying(concept, self.docs):
                carriers[path].append(name)
        self.assertTrue(
            any(len(names) >= 3 for names in carriers.values()),
            f"the concepts are scattered across documents: {dict(carriers)}",
        )


class TestTheConceptGateDetectsRemoval(unittest.TestCase):
    """Non-vacuity, proved by mutation on synthetic and copied text."""

    def test_an_empty_corpus_fails_every_concept(self):
        self.assertEqual(missing_concepts({}), sorted(CONCEPTS))

    def test_unrelated_prose_fails_every_concept(self):
        prose = {
            "docs/UNRELATED.md": flatten(
                "The pipeline writes NDJSON marts to a Lakehouse destination. "
                "Every gold row carries a run identifier so two runs never merge."
            )
        }
        self.assertEqual(missing_concepts(prose), sorted(CONCEPTS))

    def test_a_reasonable_rewording_still_passes(self):
        reworded = {
            "docs/REWRITTEN.md": flatten(
                """
                Start with the blocking findings when you read a run; nothing else
                matters until those walls are cleared.

                A Data Agent that always answers is riskier than one that declines
                more often, because a single confident invention is misleading.

                When an object comes back not evaluated, gather more evidence and
                run again. Do not score the same evidence again.

                The Approved for Copilot flag is an author's own claim about their
                content. It is not evidence of quality and cannot move a score.

                Exposing every table through the AI data schema hurts precision
                instead of helping; a narrower selection scores better.
                """
            )
        }
        self.assertEqual(missing_concepts(reworded), [])

    def test_scattered_keywords_do_not_satisfy_a_concept(self):
        concept = CONCEPTS["endorsement_is_self_attestation"]
        filler = " lorem ipsum" * 200
        scattered = {
            "docs/SCATTERED.md": flatten(
                "Approved for Copilot appears in the endorsement column."
                + filler
                + "Somewhere much later the author's own claim is mentioned."
                + filler
                + "And later still, it is not evidence of anything."
            )
        }
        self.assertIsNone(
            covering_passage(scattered["docs/SCATTERED.md"], concept),
            "facets spread across an entire document must not count as an explanation",
        )
        self.assertIn("endorsement_is_self_attestation", missing_concepts(scattered))

    def test_deleting_the_human_guide_leaves_concepts_unhomed(self):
        """The load-bearing test: Skill present, guide gone, gate must fail."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            shutil.copytree(
                os.path.join(REPO_ROOT, "docs"), os.path.join(root, "docs")
            )
            shutil.copy2(
                os.path.join(REPO_ROOT, "README.md"), os.path.join(root, "README.md")
            )
            skill_source = os.path.join(REPO_ROOT, SKILL_RELATIVE.replace("/", os.sep))
            skill_target = os.path.join(root, SKILL_RELATIVE.replace("/", os.sep))
            os.makedirs(os.path.dirname(skill_target))
            shutil.copy2(skill_source, skill_target)

            self.assertEqual(missing_concepts(human_docs(root)), [])

            os.remove(os.path.join(root, "docs", "INTERPRETING_RESULTS.md"))
            missing = missing_concepts(human_docs(root))

        self.assertTrue(
            missing,
            "deleting the human guide left every concept satisfied; the gate would "
            "not notice the Skill becoming the only home of the guidance",
        )

    def test_stripping_one_concept_fails_only_that_concept(self):
        """A surgical mutation: remove one passage, keep the rest of the guide."""
        docs = human_docs()
        for name, concept in CONCEPTS.items():
            with self.subTest(concept=name):
                mutated = {}
                for path, text in docs.items():
                    while (passage := covering_passage(text, concept)) is not None:
                        text = text.replace(passage, " ", 1)
                    mutated[path] = text
                self.assertIn(name, missing_concepts(mutated))


if __name__ == "__main__":
    unittest.main()
