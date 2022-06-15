import copy
import keyword
import logging
import typing
from dataclasses import field, make_dataclass
from typing import Dict

from pythoncommons.file_parser.input_file_parser import DiagnosticConfig, GenericLineByLineParser
from pythoncommons.file_parser.parser_config_reader import ParserConfigReader, GREEDY_FIELD_POSTFIX

from musicmanager.commands.addnewmixestolisten.config import ParserConfig

LOG = logging.getLogger(__name__)


class NewMixesToListenInputFileParser:
    ParsedListenToMixRow = None

    def __init__(self, config_reader: ParserConfigReader):
        self._validate(config_reader)
        diagnostic_config = DiagnosticConfig(print_date_lines=True,
                                             print_multi_line_block_headers=True,
                                             print_multi_line_blocks=True)
        self.generic_parser_config = config_reader.config
        self.extended_config: ParserConfig = config_reader.extended_config
        self.extended_config.fields_by_sheet_name = {v.name_in_sheet: v for k, v in
                                                     self.extended_config.parser_settings.fields.items()}
        self.extended_config.fields_by_short_name = {k: v for k, v in
                                                     self.extended_config.parser_settings.fields.items()}
        LOG.info("Initialized parser config")

        key_conv_func = ParsedListenToMixRowFieldUtils.convert_config_field_name_to_dataclass_property_name
        self.dataclass_fields = {key_conv_func(k): (key_conv_func(k), typing.Any, field(default=None, init=False)) for k, v in
                                 config_reader.extended_config.fields_by_short_name.items()}

        if not self.dataclass_fields:
            raise ValueError("Dataclass fields are empty!")

        NewMixesToListenInputFileParser.ParsedListenToMixRow = make_dataclass('ParsedListenToMixRow', list(self.dataclass_fields.values()))

        self.generic_line_by_line_parser = GenericLineByLineParser(
            self.generic_parser_config,
            diagnostic_config=diagnostic_config)

    @staticmethod
    def _validate(config_reader):
        # Cross-check fields from parser config vs. Extended config
        generic_fields = set(config_reader.config.generic_parser_settings.fields.keys())
        extended_fields = set(config_reader.extended_config.parser_settings.fields.keys())
        if generic_fields != extended_fields:
            diff = generic_fields.difference(extended_fields)
            raise ValueError(
                "Difference in generic fields vs. extended fields. Difference: {}, Generic: {}, Extended: {}".format(
                    diff, generic_fields, extended_fields))

    def parse(self, file: str):
        return self.generic_line_by_line_parser.parse(file,
                                                      parsed_object_dataclass=NewMixesToListenInputFileParser.ParsedListenToMixRow,
                                                      line_to_obj_parser_func=self._create_parsed_mix_from_match_groups)

    def _create_parsed_mix_from_match_groups(self, matches: Dict[str, str]):
        self._normalize_keys(matches)
        # TODO match dates
        # match = self._match_date_line_regexes(line)
        obj = NewMixesToListenInputFileParser.ParsedListenToMixRow()

        for field_name in self._convert_field_names(self.dataclass_fields):
            key = ParsedListenToMixRowFieldUtils.convert_dataclass_property_name_to_config_field_name(field_name)
            if key in matches:
                matched_val = matches[key]
                setattr(obj, ParsedListenToMixRowFieldUtils.convert_config_field_name_to_dataclass_property_name(field_name), matched_val)
        return obj

    @staticmethod
    def _convert_field_names(f_names):
        return [ParsedListenToMixRowFieldUtils.convert_dataclass_property_name_to_config_field_name(f) for f in f_names]

    @staticmethod
    def _normalize_keys(matches):
        for key, val in copy.copy(matches).items():
            if GREEDY_FIELD_POSTFIX in key:
                key = key.replace(GREEDY_FIELD_POSTFIX, "")
                if key in matches:
                    prev_val = matches[key]
                    LOG.warning("Overriding previous value of field '%s'. Prev value: '%s', New value: '%s'", key,
                                prev_val,
                                val)
                    matches[key] = val


class ParsedListenToMixRowFieldUtils:
    KEYWORD_POSTFIX_MARKER = "__"

    @staticmethod
    def convert_config_field_name_to_dataclass_property_name(config_field_name: str):
        converted_val = config_field_name.lower()
        return ParsedListenToMixRowFieldUtils._convert_keyword_if_any(converted_val)

    @staticmethod
    def convert_dataclass_property_name_to_config_field_name(dc_prop_name: str, lower=False):
        dc_prop_name = ParsedListenToMixRowFieldUtils._reverse_convert_keyword_if_any(dc_prop_name)
        if lower:
            return dc_prop_name.lower()
        return dc_prop_name.upper()

    @classmethod
    def _convert_keyword_if_any(cls, field_name):
        # Dataclass attribute names can't be keywords, e.g. 'from'
        # so it is converted to from__
        # TODO Is this safe to do so only here?
        if keyword.iskeyword(field_name):
            return field_name + cls.KEYWORD_POSTFIX_MARKER
        return field_name

    @classmethod
    def _reverse_convert_keyword_if_any(cls, field_name):
        if field_name.endswith(cls.KEYWORD_POSTFIX_MARKER):
            postfix_len = len(cls.KEYWORD_POSTFIX_MARKER)
            return field_name[:-postfix_len]
        return field_name

    @staticmethod
    def safe_get_attr(parsed_obj: NewMixesToListenInputFileParser.ParsedListenToMixRow, attr_name: str):
        safe_attr_name = ParsedListenToMixRowFieldUtils._convert_keyword_if_any(attr_name)
        return getattr(parsed_obj, safe_attr_name)
