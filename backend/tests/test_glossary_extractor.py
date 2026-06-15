import json

import pytest

from novel_translation_backend.graph.nodes.glossary_extractor import (
    _parse_proposed_terms,
)


def test_parse_proposed_terms_includes_short_description() -> None:
    response = json.dumps(
        [
            {
                "chinese": "神光宗",
                "proposed_english": "Shenguang Sect",
                "description": "A prominent cultivation sect.",
            }
        ]
    )

    terms = _parse_proposed_terms(response)

    assert terms[0]["description"] == "A prominent cultivation sect."


def test_parse_proposed_terms_rejects_description_over_ten_words() -> None:
    response = json.dumps(
        [
            {
                "chinese": "神光宗",
                "proposed_english": "Shenguang Sect",
                "description": "One two three four five six seven eight nine ten eleven",
            }
        ]
    )

    with pytest.raises(ValueError, match="at most 10 words"):
        _parse_proposed_terms(response)
