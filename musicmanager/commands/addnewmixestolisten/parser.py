import copy
import keyword
import logging
import typing
from dataclasses import field, make_dataclass
from typing import Dict

from pythoncommons.file_parser.input_file_parser import DiagnosticConfig, GenericLineByLineParser
from pythoncommons.file_parser.parser_config_reader import ParserConfigReader

from musicmanager.commands.addnewmixestolisten.config import ParserConfig, Fields

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
        self.extended_config.fields.post_init(self.extended_config.parser_settings.fields)
        LOG.info("Initialized parser config")
        NewMixesToListenInputFileParser.ParsedListenToMixRow = make_dataclass('ParsedListenToMixRow', self.extended_config.fields.get_list_of_dataclass_fields())

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
                "Difference in generic fields vs. extended fields. "
                "Difference: {}, Generic: {}, Extended: {}".format(diff, generic_fields, extended_fields))

    def parse(self, file: str):
        return self.generic_line_by_line_parser.parse(file,
                                                      parsed_object_dataclass=NewMixesToListenInputFileParser.ParsedListenToMixRow,
                                                      line_to_obj_parser_func=self._create_parsed_mix_from_match_groups)

    def _create_parsed_mix_from_match_groups(self, matches: Dict[str, str]):
        return self.extended_config.fields.create_object_by_matches(obj_type=NewMixesToListenInputFileParser.ParsedListenToMixRow, matches=matches)
