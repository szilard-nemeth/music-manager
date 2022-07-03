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


@dataclass(eq=True, frozen=True)
class Field:
    mix_field: MixField
    name: str
    dataclass_name: str


@dataclass
class Fields:
    KEYWORD_POSTFIX_MARKER = "__"

    fields: List[Field] = field(default_factory=list)
    by_sheet_name: Dict[str, Field] = field(default_factory=dict)
    by_short_name: Dict[str, Field] = field(default_factory=dict)
    dataclass_fields = None

    def post_init(self, fields: Dict[str, MixField]):
        self.fields = self._create_field_objs(fields)
        self.by_sheet_name = {field.mix_field.name_in_sheet: field for field in self.fields}
        self.by_short_name = {field.name: field for field in self.fields}

        key_conv_func = self._convert_to_dataclass_prop_name
        self.dataclass_fields = {key_conv_func(k): (key_conv_func(k), typing.Any, field(default=None, init=False)) for k, v in
                                 self.by_short_name.items()}
        if not self.dataclass_fields:
            raise ValueError("Dataclass fields are empty!")

    @staticmethod
    def _create_field_objs(src_fields: Dict[str, MixField]):
        fields = []
        for field_name, mix_field in src_fields.items():
            field_name = Fields._convert_field_to_field_key(field_name)
            dataclass_name = Fields._convert_to_dataclass_prop_name(field_name)
            fields.append(Field(mix_field, field_name, dataclass_name))
        return fields

    def get_list_of_dataclass_fields(self):
        return list(self.dataclass_fields.values())

    @staticmethod
    def _convert_to_dataclass_prop_name(config_field_name: str):
        converted_val = Fields._convert_field_to_field_key(config_field_name)
        return Fields._convert_keyword_if_any(converted_val)

    @staticmethod
    def _convert_keyword_if_any(field_name):
        # Dataclass attribute names can't be keywords, e.g. 'from'
        # so it is converted to from__
        if keyword.iskeyword(field_name):
            return field_name + Fields.KEYWORD_POSTFIX_MARKER
        return field_name

    @staticmethod
    def safe_get_attr(parsed_obj: Any, attr_name: str):
        safe_attr_name = Fields._convert_keyword_if_any(attr_name)
        return getattr(parsed_obj, safe_attr_name)

    def _convert_matches_to_field_dict(self, matches):
        self._normalize_keys(matches)
        ret = {}
        for k, v in matches.items():
            key = self._convert_field_to_field_key(k)
            field = self.by_short_name[key]
            ret[field] = v
        return ret

    @staticmethod
    def _convert_field_to_field_key(k):
        return k.lower()

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
        conv_matches: Dict[Field, str] = self._convert_matches_to_field_dict(matches)
        # TODO match dates
        # match = self._match_date_line_regexes(line)
        obj = obj_type()
        for field, val in conv_matches.items():
            prop_name = self._convert_to_dataclass_prop_name(field.name)
            setattr(obj, prop_name, val)
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
