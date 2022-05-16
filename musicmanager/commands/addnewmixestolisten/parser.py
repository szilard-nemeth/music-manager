import copy
import logging
from dataclasses import field, make_dataclass
from typing import Dict

import typing
from pythoncommons.file_parser.input_file_parser import DiagnosticConfig, GenericLineByLineParser
from pythoncommons.file_parser.parser_config_reader import ParserConfigReader, RegexGenerator, \
    GREEDY_FIELD_POSTFIX

from musicmanager.commands.addnewmixestolisten.config import ParserConfig

LOG = logging.getLogger(__name__)


class NewMixesToListenInputFileParser:
    ParsedListenToMixRow = None

    def __init__(self, config_reader: ParserConfigReader):
        diagnostic_config = DiagnosticConfig(print_date_lines=True,
                                             print_multi_line_block_headers=True,
                                             print_multi_line_blocks=True)

        self.generic_parser_config = config_reader.config
        self.extended_config: ParserConfig = config_reader.extended_config
        self.extended_config.fields_by_sheet_name = {v.name_in_sheet: v for k, v in
                                                     self.extended_config.parser_settings.fields.items()}
        self.extended_config.fields_by_short_name = {k.lower(): v for k, v in
                                                     self.extended_config.parser_settings.fields.items()}
        LOG.info("Initialized parser config")

        self.dataclass_fields = {k: (k, typing.Any, field(default=None, init=False)) for k, v in
                                 config_reader.extended_config.fields_by_short_name.items()}

        if not self.dataclass_fields:
            raise ValueError("Dataclass fields are empty!")

        NewMixesToListenInputFileParser.ParsedListenToMixRow = make_dataclass('ParsedListenToMixRow',
                                                                              list(self.dataclass_fields.values()))

        self.generic_line_by_line_parser = GenericLineByLineParser(
            self.generic_parser_config,
            regex=RegexGenerator.create_final_regex(self.generic_parser_config),
            diagnostic_config=diagnostic_config)

    def parse(self, file: str):
        return self.generic_line_by_line_parser.parse(file,
                                                      parsed_object_dataclass=NewMixesToListenInputFileParser.ParsedListenToMixRow,
                                                      line_to_obj_parser_func=self._create_parsed_mix_from_match_groups)

    def _create_parsed_mix_from_match_groups(self, matches: Dict[str, str]):
        self._normalize_keys(matches)
        # TODO match dates
        # match = self._match_date_line_regexes(line)
        obj = NewMixesToListenInputFileParser.ParsedListenToMixRow()
        for field_name in self.dataclass_fields:
            if field_name in matches:
                matched_val = matches[field_name]
                setattr(obj, field_name, matched_val)
        return obj

    @staticmethod
    def _normalize_keys(matches):
        for key, val in copy.copy(matches).items():
            if GREEDY_FIELD_POSTFIX in key:
                key = key.replace(GREEDY_FIELD_POSTFIX, "")
                matches[key] = val
                if key in matches:
                    prev_val = matches[key]
                    LOG.warning("Overriding previous value of field '%s'. Prev value: '%', New value: '%s'", key,
                                prev_val,
                                val)
                    matches[key] = val
