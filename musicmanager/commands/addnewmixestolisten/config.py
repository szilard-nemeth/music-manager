import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Pattern

from dataclasses_json import dataclass_json, LetterCase
from pythoncommons.date_utils import DateUtils
from pythoncommons.file_utils import JsonFileUtils
from pythoncommons.string_utils import auto_str

LOG = logging.getLogger(__name__)
VAR_PATTERN: str = r'VAR\(([a-zA-Z_]+)\)'
DEFAULT_PARSE_PREFIX_SEPARATOR = ":"
DEFAULT_ALLOWED_VALUES_SEPARATOR = ","
GREEDY_FIELD_POSTFIX = "_greedy"


class FieldParseType(Enum):
    REGEX = "regex"
    BOOL = "bool"
    INT = "int"


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class MixField:
    name_in_sheet: str
    human_readable_name: str
    parse_type: FieldParseType
    optional: bool
    precedence: int or None = field(default=100)
    eat_greedy_without_parse_prefix: bool or None = field(default=False)
    parse_prefix: str or None = field(default=None)
    parse_regex_value: str or None = field(default=None)
    allowed_values: str or None = field(default=None)

    def __post_init__(self):
        if self.allowed_values:
            self.allowed_values_list = self.allowed_values.split(",")


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class GenericParserSettings:
    fields: Dict[str, MixField] = field(default_factory=dict)
    date_formats: List[str] = field(default_factory=list)  # https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ParserConfig:
    generic_parser_settings: GenericParserSettings
    fields_by_regexes: Dict[str, str] = field(default_factory=dict)
    fields_by_sheet_name: Dict[str, MixField] = field(default_factory=dict)
    fields_by_short_name: Dict[str, MixField] = field(default_factory=dict)
    date_regexes: List[Pattern] = field(default_factory=list)

    def __post_init__(self):
        pass
        LOG.info("Initialized parser config")


class RegexCreator:
    @staticmethod
    def get_regexes(field_objects: Dict[str, MixField]):
        # Order dict by precedence
        field_objects = {k: v for k, v in sorted(field_objects.items(), key=lambda item: item[1].precedence)}

        regex_dict: Dict[str, str] = {}
        used_group_names = {}
        for field_name, field_object in field_objects.items():
            group_name = field_name.lower()
            if group_name not in used_group_names:
                used_group_names[group_name] = True
                regex_dict[group_name] = RegexCreator._create_regex(group_name, field_object)
            else:
                raise ValueError("Group name is already used in regex: {}".format(group_name))
            if field_object.eat_greedy_without_parse_prefix:
                field_key = group_name + GREEDY_FIELD_POSTFIX
                regex_dict[field_key] = RegexCreator._create_regex(field_key, field_object, use_parse_prefix=False)
        return regex_dict

    @staticmethod
    def _create_regex(group_name, field_object: MixField, use_parse_prefix=True):
        regex_value = field_object.parse_regex_value

        parse_prefix = ""
        if use_parse_prefix:
            parse_prefix = field_object.parse_prefix
            if not parse_prefix:
                parse_prefix = ""
            else:
                parse_prefix += DEFAULT_PARSE_PREFIX_SEPARATOR

        if field_object.parse_type == FieldParseType.REGEX and regex_value.startswith("\"") and regex_value.endswith("\""):
            regex_value = regex_value[1:-1]
        if field_object.parse_type == FieldParseType.INT:
            regex_value = r"\d+"
        elif field_object.parse_type == FieldParseType.BOOL:
            regex_value = "|".join(field_object.allowed_values_list)
        grouped_regex = f"(?P<{group_name}>{parse_prefix}{regex_value})"
        if field_object.optional:
            grouped_regex += "*"
        return grouped_regex

    @staticmethod
    def _get_inner_group_grouped_regex(group_name, regex_value):
        open_idx = regex_value.find('(')
        close_idx = regex_value.rfind(')')
        quantifier = regex_value[close_idx + 1]
        if quantifier not in ["*", "?", "+"]:
            quantifier = ""
        start = regex_value[:open_idx]
        end = regex_value[close_idx + 1:]
        group = regex_value[open_idx + 1:close_idx] + quantifier
        grouped_regex = f"(?P<{group_name}>{group})"
        new_regex_value = f"{start}{grouped_regex}{end}"
        return new_regex_value

    @staticmethod
    def convert_date_formats_to_patterns(date_formats):
        mappings = {
            "%m": "\\d\\d",
            "%d": "\\d\\d",
            "%Y": "\\d\\d\\d\\d",
            ".": "\\."
        }
        regexes: List[Pattern] = []
        for fmt in date_formats:
            curr_regex = fmt
            for orig, pattern in mappings.items():
                curr_regex = curr_regex.replace(orig, pattern)
            curr_regex += "$"
            regexes.append(re.compile(curr_regex))
        return regexes


@auto_str
class ParserConfigReader:
    def __init__(self, data):
        self.data = data
        self.config: ParserConfig = self._parse()
        self._validate()
        self._post_init()

    @staticmethod
    def read_from_file(dir=None, filename=None):
        if filename:
            parser_conf_file = filename
        elif dir:
            parser_conf_file = os.path.join(dir, "parserconfig.json")
        else:
            parser_conf_file = "parserconfig.json"

        data_dict = JsonFileUtils.load_data_from_json_file(parser_conf_file)
        return ParserConfigReader(data_dict)

    def _parse(self):
        parser_config = ParserConfig.from_json(json.dumps(self.data))
        LOG.info("Parser config: %s", parser_config)
        return parser_config

    def _validate(self):
        self._check_variables()
        self._validate_date_formats(self.config.generic_parser_settings.date_formats)
        self._validate_alllowed_values()

    def _validate_alllowed_values(self):
        for field_name, field_object in self.config.generic_parser_settings.fields.items():
            if field_object.parse_type == FieldParseType.BOOL and not field_object.allowed_values:
                raise ValueError(
                    "Parse type is set to '{}' on field '{}', but allowed values are not specified!".format(
                        FieldParseType.BOOL.value, field_name
                    ))

    def _check_variables(self):
        for field_name, field_object in self.config.generic_parser_settings.fields.items():
            if field_object.parse_type != FieldParseType.REGEX:
                continue
            vars = re.findall(VAR_PATTERN, field_object.parse_regex_value)
            vars_set = set(vars)
            if vars_set:
                LOG.debug("Find variables in field '%s': '%s'", field_name, field_object.value)
                available_vars = self.config.generic_parser_settings.variables
                diff = set(vars_set).difference(set(available_vars.keys()))
                if diff:
                    raise ValueError("Unknown variables '{}' in {}: {}. Available variables: {}"
                                     .format(diff, field_name, field_object.value, available_vars.keys()))
                self._resolve_variables(available_vars, field_name, field_object, vars_set)

    @staticmethod
    def _resolve_variables(available_vars, field_name, field_object: MixField, vars_set):
        original_value = str(field_object.parse_regex_value)
        LOG.debug("Resolving variables in string: %s", original_value)
        new_value = str(original_value)

        for var in vars_set:
            new_value = new_value.replace(f"VAR({var})", available_vars[var])
        LOG.debug("Resolved variables for '%s'. Old: %s, New: %s", field_name, original_value, new_value)
        field_object.parse_regex_value = new_value

    def _post_init(self):
        self.config.fields_by_regexes = RegexCreator.get_regexes(self.config.generic_parser_settings.fields)
        self.config.fields_by_sheet_name = {v.name_in_sheet: v for k, v in self.config.generic_parser_settings.fields.items()}
        self.config.fields_by_short_name = {k.lower(): v for k, v in self.config.generic_parser_settings.fields.items()}
        LOG.info("FINAL REGEX: %s", self.config.fields_by_regexes)
        self.config.date_regexes = RegexCreator.convert_date_formats_to_patterns(self.config.generic_parser_settings.date_formats)

    @staticmethod
    def _validate_date_formats(format_strings):
        for fmt in format_strings:
            LOG.debug("Formatting current date with format '%s': %s", fmt, DateUtils.now_formatted(fmt))

    def __repr__(self):
        return self.__str__()
