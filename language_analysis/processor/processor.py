from __future__ import annotations

import collections
import random
from typing import Any
import warnings
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import stanza

from .schema import (
    ConceptOccurrence,
    ConceptProfile,
    ConceptType,
    LinguisticProfile,
    NumberAndRatio,
    PersonalConceptProfile,
    PersonalMediaAnalysis,
    PersonalTimeRangeStats,
)


def extract_lemmas(
    doc: stanza.Document,
) -> Iterator[tuple[str, ConceptOccurrence]]:
    for sentence in doc.sentences:
        for word in sentence.words:
            # Skip punctuation, pronouns and other non-content words
            if (
                word.upos in {"PUNCT", "PRON", "DET", "ADP", "CCONJ", "SCONJ", "AUX"}
                or word.start_char is None
            ):
                continue

            concept = word.lemma
            example = ConceptOccurrence(
                context=sentence.text,
                start_char=word.start_char - sentence.tokens[0].start_char,
                end_char=word.end_char - sentence.tokens[0].start_char,
            )
            yield concept, example


def extract_phrasal_verbs(
    doc: stanza.Document,
) -> Iterator[tuple[str, ConceptOccurrence]]:
    for sentence in doc.sentences:
        words_by_id = {word.id: word for word in sentence.words}
        for word in sentence.words:
            if word.deprel == "compound:prt":
                if word.start_char is None:
                    continue

                parts = [words_by_id[word.head], word]
                parts.sort(key=lambda x: x.start_char)

                concept = " ".join(part.lemma for part in parts)

                example = ConceptOccurrence(
                    context=sentence.text,
                    start_char=parts[0].start_char - sentence.tokens[0].start_char,
                    end_char=parts[-1].end_char - sentence.tokens[0].start_char,
                )
                yield concept, example


CONCEPT_EXTRACTORS = [
    (ConceptType.WORD, extract_lemmas),
    (ConceptType.PHRASAL_VERB, extract_phrasal_verbs),
]


def analyse_parsed_text(
    doc: stanza.Document,
    max_examples_per_concept: int = 5,
    concept_difficulties: dict[str, float] | None = None,
) -> LinguisticProfile:
    sentences_count = len(doc.sentences)
    sentences_avg_length = (
        sum(len(sentence.words) for sentence in doc.sentences) / sentences_count
        if sentences_count > 0
        else 0
    )

    pos_counts = collections.Counter(
        word.upos for sentence in doc.sentences for word in sentence.words
    )

    # Convert pos_counts to NumberAndRatio format
    total_pos = sum(pos_counts.values())
    pos_stats = {
        pos: NumberAndRatio(number=count, ratio=count / total_pos)
        for pos, count in pos_counts.items()
    }

    concepts = {}

    for concept_type, extractor in CONCEPT_EXTRACTORS:
        concept_entries: list[Any] = []
        concept_dict = {}

        for concept, example in extractor(doc):
            new_concept_difficulty = (
                concept_difficulties.get(concept) if concept_difficulties else None
            )

            if concept not in concept_dict:
                concept_dict[concept] = ConceptProfile(
                    concept=concept,
                    num_occurrences=1,
                    examples=[example],
                    difficulty=new_concept_difficulty,
                )
            else:
                concept_dict[concept].num_occurrences += 1

                # Keep a limited number of examples
                if len(concept_dict[concept].examples) < max_examples_per_concept:
                    concept_dict[concept].examples.append(example)
                else:
                    # Randomly replace an existing example with probability 1/n
                    # where n is the number of occurrences seen so far
                    import random

                    n = concept_dict[concept].num_occurrences
                    if random.random() < 1 / n:
                        replace_idx = random.randrange(max_examples_per_concept)
                        concept_dict[concept].examples[replace_idx] = example

        concept_entries.extend(concept_dict.values())
        concepts[concept_type] = concept_entries

    unique_concept_difficulties = [
        entry.difficulty
        for entries in concepts.values()
        for entry in entries
        if entry.difficulty is not None
    ]
    overall_difficulty = (
        sum(unique_concept_difficulties) / len(unique_concept_difficulties)
        if len(unique_concept_difficulties) > 0
        else None
    )

    return LinguisticProfile(
        analysis_version="0.1",
        concepts=concepts,
        pos_stats=pos_stats,
        sentences_count=sentences_count,
        sentences_avg_length=sentences_avg_length,
        difficulty=overall_difficulty,
    )


class LinguisticProcessor:
    def __init__(
        self,
        difficulty_csv_path: str = str(Path(__file__).parent / "data/difficulty.csv"),
        max_examples_per_concept: int = 2,
    ):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning)
            self.nlp = stanza.Pipeline(
                lang="en",
                processors="tokenize,mwt,pos,lemma,depparse",
                verbose=False,
            )

        df_difficulty = pd.read_csv(difficulty_csv_path)

        self.concept_difficulties = df_difficulty.set_index("word")["rating"].to_dict()
        self.max_examples_per_concept = max_examples_per_concept

    def process(self, text: str) -> LinguisticProfile:
        doc = self.nlp(text)
        return analyse_parsed_text(
            doc,
            concept_difficulties=self.concept_difficulties,
            max_examples_per_concept=self.max_examples_per_concept,
        )


def mock_personal_analysis(
    user_id: str, media_profile: LinguisticProfile
) -> PersonalMediaAnalysis:
    """
    This function simulates behaviour of the API endpoint that will be provided by the Glite backend.
    """
    # Create a local random number generator seeded with user_id
    rng = random.Random(hash(user_id))

    # Convert concepts to personal concepts
    personal_concepts: dict[ConceptType, list[PersonalConceptProfile]] = {}
    for concept_type, concepts in media_profile.concepts.items():
        personal_concepts[concept_type] = []
        for concept in concepts:
            # Generate random personal data
            in_learning = rng.random() < 0.3
            prob_known = rng.random() if not in_learning else rng.random() * 0.5

            personal_difficulty = None
            if concept.difficulty is not None:
                # Randomly adjust difficulty by ±10%
                personal_difficulty = concept.difficulty * (0.9 + 0.2 * rng.random())

            personal_concepts[concept_type].append(
                PersonalConceptProfile(
                    **concept.model_dump(),
                    personal_difficulty=personal_difficulty,
                    in_learning=in_learning,
                    prob_known=prob_known,
                )
            )

    # Generate personal time range stats if original has time ranges
    personal_time_ranges = None
    if media_profile.time_ranges:
        personal_time_ranges = []
        for tr in media_profile.time_ranges:
            # Generate random number of unknown concepts (0-5)
            num_unknown = round(rng.random() * 5)
            # Calculate ratio based on total concepts in this range
            total_concepts = sum(
                len(concepts) for concepts in media_profile.concepts.values()
            )
            ratio = num_unknown / total_concepts if total_concepts > 0 else 0
            est_unknown = NumberAndRatio(number=num_unknown, ratio=ratio)

            personal_difficulty = None
            if tr.difficulty is not None:
                # Randomly adjust difficulty by ±10%
                personal_difficulty = tr.difficulty * (0.9 + 0.2 * rng.random())

            personal_time_ranges.append(
                PersonalTimeRangeStats(
                    **tr.model_dump(),
                    personal_difficulty=personal_difficulty,
                    estimated_unknown_concepts=est_unknown,
                )
            )

    # Generate estimated unknown concepts per type
    est_unknown_concepts = {}
    for ctype, concepts in media_profile.concepts.items():
        num_unknown = round(rng.random() * len(concepts))
        ratio = num_unknown / len(concepts) if concepts else 0
        est_unknown_concepts[ctype] = NumberAndRatio(number=num_unknown, ratio=ratio)

    # Generate some recommended concepts
    all_concepts = [
        concept.concept
        for concepts in media_profile.concepts.values()
        for concept in concepts
    ]
    recommended = (
        rng.sample(all_concepts, min(5, len(all_concepts))) if all_concepts else None
    )

    # Generate personal difficulty by adjusting media difficulty by ±10%
    personal_difficulty = None
    if media_profile.difficulty is not None:
        personal_difficulty = media_profile.difficulty * (0.9 + 0.2 * rng.random())

    return PersonalMediaAnalysis(
        concepts=personal_concepts,
        personal_difficulty=personal_difficulty,
        time_ranges=personal_time_ranges,
        estimated_unknown_concepts=est_unknown_concepts,
        recommended_concepts=recommended,
    )
