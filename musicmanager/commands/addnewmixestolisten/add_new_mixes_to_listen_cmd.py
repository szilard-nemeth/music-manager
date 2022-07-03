import logging
import os
from dataclasses import fields
from enum import Enum
from pprint import pformat
from typing import List, Dict

from googleapiwrapper.google_sheet import GSheetOptions, GSheetWrapper
from pythoncommons.file_parser.parser_config_reader import GenericLineParserConfig, ParserConfigReader
from pythoncommons.file_utils import FindResultType
from pythoncommons.project_utils import SimpleProjectUtils
from pythoncommons.result_printer import BasicResultPrinter

from musicmanager.commands.addnewmixestolisten.config import ParserConfig, Fields, Field
from musicmanager.commands.addnewmixestolisten.parser import NewMixesToListenInputFileParser
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
        super().__init__()
        self.config = AddNewMixesToListenCommandConfig(args, parser=parser)
        self.data = None
        self.header = None

    @staticmethod
    def create_parser(subparsers):
        parser = subparsers.add_parser(
            CommandType.ADD_NEW_MIXES_TO_LISTEN.name,
            help="Add new mixes to listen." "Example: --src_file /tmp/file1",
        )
        parser.add_argument('--src_file', type=str)
        parser.set_defaults(func=AddNewMixesToListenCommand.execute)

    @staticmethod
    def execute(args, parser=None):
        command = AddNewMixesToListenCommand(args)
        command.run()

    def run(self):
        LOG.info(f"Starting to add new mixes to listen to sheet. \n Config: {str(self.config)}")
        config_reader: ParserConfigReader = ParserConfigReader.read_from_file(filename=self.config.parser_conf_json,
                                                                              obj_data_class=ParserConfig,
                                                                              config_type=GenericLineParserConfig)
        LOG.info("Read project config: %s", pformat(config_reader.config))
        parser = NewMixesToListenInputFileParser(config_reader)
        parsed_objs = parser.parse(self.config.src_file)
        self.header = list(parser.extended_config.fields.by_sheet_name.keys())
        if self.config.operation_mode == OperationMode.GSHEET:
            col_indices_by_of_fields = self.config.gsheet_wrapper.get_column_indices_of_header(self.header)
        else:
            col_indices_by_of_fields = {col_name: idx for idx, col_name in enumerate(self.header)}
        self.data = DataConverter.convert_data_to_rows(parsed_objs, parser.extended_config.fields, col_indices_by_of_fields)

        if not self.header:
            raise ValueError("Header is empty")

        if not self.data:
            raise ValueError("Data is empty")

        BasicResultPrinter.print_table(self.data, self.header)
        if self.config.operation_mode == OperationMode.GSHEET:
            LOG.info("Updating Google sheet with data...")
            self.update_gsheet()
        elif self.config.operation_mode == OperationMode.DRY_RUN:
            LOG.info("[DRY-RUN] Would add the following rows to Google Sheets: ")
            LOG.info(self.data)
        LOG.info("Finished adding new mixes to listen")

    def update_gsheet(self):
        self.config.gsheet_wrapper.write_data_to_new_rows(self.header, self.data, clear_range=False)


class DataConverter:
    TITLE_MAX_LENGTH = 50
    LINK_MAX_LENGTH = 20
    row_stats = None

    @classmethod
    def convert_data_to_rows(cls, parsed_mixes: List[NewMixesToListenInputFileParser.ParsedListenToMixRow],
                             fields_obj: Fields,
                             col_indices_by_sheet_name: Dict[str, int]) -> List[List[str]]:
        sheet_list_of_rows: List[List[str]] = []
        field_names = [field.name for field in fields_obj.fields]
        cls.row_stats: RowStats = RowStats(field_names)
        for parsed_mix in parsed_mixes:
            row, values_by_fields = DataConverter._convert_parsed_mix(parsed_mix, fields_obj, col_indices_by_sheet_name)
            DataConverter.update_row_stats(values_by_fields)
            sheet_list_of_rows.append(row)
        cls.row_stats.print_stats()
        return sheet_list_of_rows

    @classmethod
    def _convert_parsed_mix(cls, parsed_mix: NewMixesToListenInputFileParser.ParsedListenToMixRow,
                            fields_obj: Fields,
                            col_indices_by_sheet_name) -> NewMixesToListenInputFileParser.ParsedListenToMixRow:
        field_names = [field.name for field in fields_obj.fields]
        row: List[str] = [""] * len(field_names)
        values_by_fields: Dict[str, str] = {}
        for field_name in field_names:
            field_obj: Field = fields_obj.by_short_name[field_name]
            col_idx = col_indices_by_sheet_name[field_obj.mix_field.name_in_sheet]
            obj_value = Fields.safe_get_attr(parsed_mix, field_name)
            row[col_idx] = obj_value
            values_by_fields[field_name] = obj_value
        return row, values_by_fields

    @classmethod
    def update_row_stats(cls, values_by_fields):
        cls.row_stats.update(values_by_fields)
