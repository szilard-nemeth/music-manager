import copy
import logging
import pprint
import re
from dataclasses import make_dataclass, field
from enum import Enum
from typing import Pattern, List, Dict

import typing
from pythoncommons.file_utils import FileUtils

from musicmanager.commands.addnewmixestolisten.config import ParserConfig, GREEDY_FIELD_POSTFIX

LOG = logging.getLogger(__name__)


class InfoType(Enum):
    PARSED_MIXES = ("PARSED_MIXES", "Parsed mixes: %s")
    MATCH_OBJECT = ("MATCH_OBJECT", "Match object: %s")

    def __init__(self, value, log_pattern):
        self.log_pattern = log_pattern


class DiagnosticConfig:
    def __init__(self,
                 print_match_objs: bool = False,
                 print_parsed_mixes: bool = True):
        self.print_match_objs = print_match_objs
        self.print_parsed_mixes = print_parsed_mixes
        self.conf_dict: Dict[InfoType, bool] = {InfoType.MATCH_OBJECT: self.print_match_objs,
                                                InfoType.PARSED_MIXES: self.print_parsed_mixes}


class DiagnosticPrinter:
    def __init__(self, diagnostic_config: DiagnosticConfig):
        self.diagnostic_config = diagnostic_config

    def print_line(self, line, info_type: InfoType):
        enabled = self.diagnostic_config.conf_dict[info_type]
        if enabled:
            LOG.debug(info_type.log_pattern, line)

    def pretty_print(self, obj, info_type: InfoType):
        enabled = self.diagnostic_config.conf_dict[info_type]
        if enabled:
            LOG.debug(info_type.log_pattern, pprint.pformat(obj))


class InputFileParser:
    ParsedListenToMixRow = None
    def __init__(self, config: ParserConfig, diagnostic_config: DiagnosticConfig):
        self.printer = DiagnosticPrinter(diagnostic_config)
        self.config: ParserConfig = config
        self.dataclass_fields = {k: (k, typing.Any, field(default=None, init=False)) for k, v in self.config.fields_by_short_name.items()}
        InputFileParser.ParsedListenToMixRow = make_dataclass('ParsedListenToMixRow', list(self.dataclass_fields.values()))
        self.parsed_mixes: List[InputFileParser.ParsedListenToMixRow] = []

    def parse(self, file: str):
        file_contents = FileUtils.read_file(file)
        # TODO change to debug level
        LOG.info("File contents: %s", file_contents)
        self.lines_of_file = file_contents.split("\n")
        for idx, line in enumerate(self.lines_of_file):
            self.parsed_mixes.append(self._process_line(line))
        self.printer.pretty_print(self.parsed_mixes, InfoType.PARSED_MIXES)

    def _process_line(self, line):
        matches: Dict[str, str] = {}
        for field_name, regex in self.config.fields_by_regexes.items():
            LOG.debug("Trying to match field with name '%s' on line '%s' with regex '%s'", field_name, line, regex)
            match = re.search(regex, line)
            if match and match.group(field_name):
                matches[field_name] = match.group(field_name)
                self.printer.print_line(match, InfoType.MATCH_OBJECT)
                line = line.replace(match.group(field_name), "")
            else:
                LOG.debug("Field with name '%s' on line '%s' with regex '%s' not found!", field_name, line, regex)
        return self._create_parsed_mix_from_match_groups(matches)

    def _match_date_line_regexes(self, line):
        for date_regex in self.config.date_regexes:  # type: Pattern
            match = date_regex.match(line)
            if match:
                return match
        return None

    def _create_parsed_mix_from_match_groups(self, matches: Dict[str, str]):
        self._normalize_keys(matches)
        # TODO match dates
        # match = self._match_date_line_regexes(line)
        obj = InputFileParser.ParsedListenToMixRow()
        for field_name in self.dataclass_fields:
            if field_name in matches:
                matched_val = matches[field_name]
                setattr(obj, field_name, matched_val)
        return obj

    def _normalize_keys(self, matches):
        for key, val in copy.copy(matches).items():
            if GREEDY_FIELD_POSTFIX in key:
                key = key.replace(GREEDY_FIELD_POSTFIX, "")
                matches[key] = val
                if key in matches:
                    prev_val = matches[key]
                    LOG.warning("Overriding previous value of field '%s'. Prev value: '%', New value: '%s'", key, prev_val, val)
                    matches[key] = val
