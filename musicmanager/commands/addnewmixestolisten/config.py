import logging
from dataclasses import dataclass, field
from typing import List, Dict

from dataclasses_json import dataclass_json, LetterCase

LOG = logging.getLogger(__name__)


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class MixField:
    name_in_sheet: str
    human_readable_name: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ParserSettings:
    fields: Dict[str, MixField] = field(default_factory=dict)


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ParserConfig:
    parser_settings: ParserSettings
    fields_by_sheet_name: Dict[str, MixField] = field(default_factory=dict)
    fields_by_short_name: Dict[str, MixField] = field(default_factory=dict)

    def __post_init__(self):
        pass
