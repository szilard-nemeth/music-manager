import copy
import keyword
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any

import typing
from dataclasses_json import dataclass_json, LetterCase
from pythoncommons.file_parser.parser_config_reader import GREEDY_FIELD_POSTFIX

LOG = logging.getLogger(__name__)


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(eq=True, frozen=True)
class MixField:
    name_in_sheet: str
    human_readable_name: str


@dataclass
class Fields:
    KEYWORD_POSTFIX_MARKER = "__"

    by_sheet_name: Dict[str, MixField] = field(default_factory=dict)
    by_short_name: Dict[str, MixField] = field(default_factory=dict)
    dataclass_fields = None

    def post_init(self, fields: Dict[str, MixField]):
        self.by_sheet_name = {v.name_in_sheet: v for k, v in fields.items()}
        self.by_short_name = {k: v for k, v in fields.items()}

        key_conv_func = self.convert_config_field_name_to_dataclass_property_name
        self.dataclass_fields = {key_conv_func(k): (key_conv_func(k), typing.Any, field(default=None, init=False)) for k, v in
                                 self.by_short_name.items()}
        if not self.dataclass_fields:
            raise ValueError("Dataclass fields are empty!")

    def get_list_of_dataclass_fields(self):
        return list(self.dataclass_fields.values())

    def convert_config_field_name_to_dataclass_property_name(self, config_field_name: str):
        converted_val = config_field_name.lower()
        return self._convert_keyword_if_any(converted_val)

    @staticmethod
    def convert_dataclass_property_name_to_config_field_name(dc_prop_name: str, lower=False):
        dc_prop_name = Fields._reverse_convert_keyword_if_any(dc_prop_name)
        if lower:
            return dc_prop_name.lower()
        return dc_prop_name.upper()

    @staticmethod
    def _convert_keyword_if_any(field_name):
        # Dataclass attribute names can't be keywords, e.g. 'from'
        # so it is converted to from__
        # TODO Is this safe to do so only here?
        if keyword.iskeyword(field_name):
            return field_name + Fields.KEYWORD_POSTFIX_MARKER
        return field_name

    @staticmethod
    def _reverse_convert_keyword_if_any(field_name):
        if field_name.endswith(Fields.KEYWORD_POSTFIX_MARKER):
            postfix_len = len(Fields.KEYWORD_POSTFIX_MARKER)
            return field_name[:-postfix_len]
        return field_name

    @staticmethod
    def safe_get_attr(parsed_obj: Any, attr_name: str):
        safe_attr_name = Fields._convert_keyword_if_any(attr_name)
        return getattr(parsed_obj, safe_attr_name)

    def _convert_matches_to_field_dict(self, matches):
        self._normalize_keys(matches)
        ret = {}
        for k, v in matches.items():
            field = self.by_short_name[k]
            ret[field] = v
        return ret

    @staticmethod
    def _normalize_keys(matches):
        for key, val in copy.copy(matches).items():
            if GREEDY_FIELD_POSTFIX in key:
                orig_key = key
                key = key.replace(GREEDY_FIELD_POSTFIX, "")
                if key in matches:
                    prev_val = matches[key]
                    LOG.warning("Overriding previous value of field '%s'. Prev value: '%s', New value: '%s'", key,
                                prev_val,
                                val)
                matches[key] = val
                del matches[orig_key]

    def create_object_by_matches(self, obj_type, matches: Dict[str, str]):
        # TODO
        conv_matches: Dict[MixField, str] = self._convert_matches_to_field_dict(matches)
        # TODO match dates
        # match = self._match_date_line_regexes(line)
        obj = obj_type()
        conv_field_names = [self.convert_dataclass_property_name_to_config_field_name(f) for f in self.dataclass_fields]
        for field_name in conv_field_names:
            if field_name in matches:
                dc_prop_name = self.convert_config_field_name_to_dataclass_property_name(field_name)
                setattr(obj, dc_prop_name, matches[field_name])
        return obj


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ParserSettings:
    fields: Dict[str, MixField] = field(default_factory=dict)


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ParserConfig:
    parser_settings: ParserSettings
    fields: Fields = Fields()

    def __post_init__(self):
        pass
