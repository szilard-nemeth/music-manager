import argparse
import datetime
import logging
import os
from dataclasses import fields
from enum import Enum
from pprint import pformat
from typing import List, Dict

from googleapiwrapper.google_sheet import GSheetOptions, GSheetWrapper
from pythoncommons.file_utils import FindResultType
from pythoncommons.project_utils import SimpleProjectUtils
from pythoncommons.result_printer import BasicResultPrinter

from musicmanager.commands.addnewmixestolisten.config import ParserConfigReader, MixField
from musicmanager.commands.addnewmixestolisten.parser import InputFileParser, DiagnosticConfig
from musicmanager.commands_common import CommandType, CommandAbs
from musicmanager.constants import LocalDirs
from musicmanager.statistics import RowStats

LOG = logging.getLogger(__name__)


class OperationMode(Enum):
    GSHEET = "GSHEET"
    DRY_RUN = "DRYRUN"


class AddNewMixesToListenCommandConfig:
    def __init__(self, args, parser=None):
        self.gsheet_wrapper = None
        self._validate(args, parser)
        self.src_file = args.src_file
        self.headers = None

    def _validate(self, args, parser):
        # TODO check existence + readability of secret file!!
        if args.gsheet and (args.gsheet_client_secret is None or
                            args.gsheet_spreadsheet is None or
                            args.gsheet_worksheet is None):
            parser.error("--gsheet requires the following mandatory arguments: \n"
                         "--gsheet-client-secret, --gsheet-spreadsheet and --gsheet-worksheet.")
        self.operation_mode = self._validate_operation_mode(args)

        if self.operation_mode == OperationMode.GSHEET:
            args.gsheet_options = GSheetOptions(args.gsheet_client_secret,
                                                args.gsheet_spreadsheet,
                                                args.gsheet_worksheet)
            self.gsheet_wrapper = GSheetWrapper(args.gsheet_options)

        parser_config_dir = SimpleProjectUtils.get_project_dir(
            basedir=LocalDirs.REPO_ROOT_DIR,
            dir_to_find="parser_config",
            find_result_type=FindResultType.DIRS,
            parent_dir="mix-listen-parser"
        )
        input_files_dir = SimpleProjectUtils.get_project_dir(
            basedir=LocalDirs.REPO_ROOT_DIR,
            dir_to_find="input_files",
            find_result_type=FindResultType.DIRS,
            parent_dir="mix-listen-parser"
        )
        self.parser_conf_json = os.path.join(parser_config_dir, "parserconfig.json")
        if not hasattr(self, "src_file"):
            self.src_file = os.path.join(input_files_dir, "mixes.txt")

    @staticmethod
    def _validate_operation_mode(args):
        if args.dry_run:
            LOG.info("Using operation mode: %s", OperationMode.DRY_RUN)
            args.operation_mode = OperationMode.DRY_RUN
        elif args.gsheet:
            LOG.info("Using operation mode: %s", OperationMode.GSHEET)
            args.operation_mode = OperationMode.GSHEET
        else:
            raise ValueError("Unknown state! Operation mode should be either "
                             "{} or {} but it is {}"
                             .format(OperationMode.DRY_RUN,
                                     OperationMode.GSHEET,
                                     args.operation_mode))
        return args.operation_mode

    def __str__(self):
        return (
            f"Source file: {self.src_file}\n"
        )


class AddNewMixesToListenCommand(CommandAbs):
    def __init__(self, args, parser=None):
        self.config = AddNewMixesToListenCommandConfig(args, parser=parser)

    @staticmethod
    def create_parser(subparsers):
        parser = subparsers.add_parser(
            CommandType.ADD_NEW_MIXES_TO_LISTEN.name,
            help="Add new mixes to listen." "Example: --src_file /tmp/file1",
        )

        #parser.add_argument('--src_file', type=argparse.FileType('r'))
        parser.add_argument('--src_file', type=str)
        parser.set_defaults(func=AddNewMixesToListenCommand.execute)

    @staticmethod
    def execute(args, parser=None):
        command = AddNewMixesToListenCommand(args)
        command.run()

    def run(self):
        LOG.info(f"Starting to add new mixes to listen to sheet. \n Config: {str(self.config)}")
        config_reader: ParserConfigReader = ParserConfigReader.read_from_file(filename=self.config.parser_conf_json)
        LOG.info("Read project config: %s", pformat(config_reader.config))

        # TODO
        # Example line of input file (various fields, but they can only be parsed in strict order with named regex groups):
        # title:"test title" addedat:2022.04.20 listenedat:2022.05.02 tracksearch:yes tracksearchdone:yes lc:2 relisten:yes genre:"progressive house" comment:"test comment__" https://www.facebook.com/100001272234500/posts/5240658839319805/  link2:http://google.com link3:http://google22.com
        parser = InputFileParser(config_reader.config, DiagnosticConfig(print_match_objs=True, print_parsed_mixes=True))
        parser.parse(self.config.src_file)
        self.header = list(parser.config.fields_by_sheet_name.keys())
        col_indices_by_sheet_name = self.config.gsheet_wrapper.get_column_indices_of_header(self.header)
        self.data = DataConverter.convert_data_to_rows(parser.parsed_mixes, parser.config.fields_by_short_name, col_indices_by_sheet_name)
        self.print_results_table()
        if self.config.operation_mode == OperationMode.GSHEET:
            LOG.info("Updating Google sheet with data...")
            self.update_gsheet()
        LOG.info("Finished adding new mixes to listen")

    def print_results_table(self):
        if not self.data:
            raise ValueError("Data is not yet set, please call sync method first!")
        BasicResultPrinter.print_table(self.data, self.header)

    def update_gsheet(self):
        if not self.data:
            raise ValueError("Data is not yet set, please call sync method first!")
        self.config.gsheet_wrapper.write_data_to_new_rows(self.header, self.data, clear_range=False)


class DataConverter:
    TITLE_MAX_LENGTH = 50
    LINK_MAX_LENGTH = 20
    row_stats = None

    @classmethod
    def convert_data_to_rows(cls, parsed_mixes: List[InputFileParser.ParsedListenToMixRow],
                             fields_by_short_name: Dict[str, MixField],
                             col_indices_by_sheet_name: Dict[str, int]) -> List[List[str]]:
        sheet_list_of_rows: List[List[str]] = []
        field_names = [field.name for field in fields(InputFileParser.ParsedListenToMixRow)]
        cls.row_stats: RowStats = RowStats(field_names)
        for parsed_mix in parsed_mixes:
            row: List[str] = DataConverter.convert_parsed_mix(parsed_mix, fields_by_short_name, col_indices_by_sheet_name)
            DataConverter.update_row_stats()
            sheet_list_of_rows.append(row)
        cls.row_stats.print_stats()
        return sheet_list_of_rows

    @classmethod
    def convert_parsed_mix(cls, parsed_mix: InputFileParser.ParsedListenToMixRow,
                           fields_by_short_name,
                           col_indices_by_sheet_name) -> InputFileParser.ParsedListenToMixRow:
        fields_list = fields(parsed_mix)
        row: List[str] = [""] * len(fields_list)
        for field in fields_list:
            field_short_name = field.name
            field_obj: MixField = fields_by_short_name[field_short_name]
            col_idx = col_indices_by_sheet_name[field_obj.name_in_sheet]
            obj_value = getattr(parsed_mix, field_short_name)
            row[col_idx] = obj_value
        return row

    @classmethod
    def update_row_stats(cls):
        # TODO
        #cls.row_stats.update({"name": name, "link": link, "date": date, "owners": owners})
        pass
