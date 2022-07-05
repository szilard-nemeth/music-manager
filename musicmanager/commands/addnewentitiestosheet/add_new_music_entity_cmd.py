import logging
import os
from enum import Enum
from pprint import pformat
from typing import List, Dict

from googleapiwrapper.google_sheet import GSheetOptions, GSheetWrapper
from pythoncommons.file_parser.parser_config_reader import GenericLineParserConfig, ParserConfigReader
from pythoncommons.file_utils import FindResultType
from pythoncommons.project_utils import SimpleProjectUtils
from pythoncommons.result_printer import BasicResultPrinter

import musicmanager.commands.addnewentitiestosheet.parser as p
from musicmanager.commands.addnewentitiestosheet.config import ParserConfig, Fields
from musicmanager.commands.addnewentitiestosheet.music_entity_creator import MusicEntityCreator, MusicEntity
from musicmanager.commands.addnewentitiestosheet.parser import MusicEntityInputFileParser
from musicmanager.commands_common import CommandType, CommandAbs
from musicmanager.constants import LocalDirs
from musicmanager.contentprovider.beatport import Beatport
from musicmanager.contentprovider.facebook import Facebook
from musicmanager.contentprovider.soundcloud import SoundCloud
from musicmanager.contentprovider.youtube import Youtube
from musicmanager.statistics import RowStats

ROWS_TO_FETCH = 3000

LOG = logging.getLogger(__name__)


class OperationMode(Enum):
    GSHEET = "GSHEET"
    DRY_RUN = "DRYRUN"


class AddNewMusicEntityCommandConfig:
    def __init__(self, args, parser=None):
        self.gsheet_wrapper = None
        self.fb_password = args.fbpwd
        self.fb_username = args.fbuser
        self._validate(args, parser)
        self.src_file = args.src_file
        self.duplicate_detection = args.duplicate_detection
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
            # TODO hardcoded filename
            self.src_file = os.path.join(input_files_dir, "mixes.txt")

        # Sanitize Facebook login data
        chars_to_remove = '\'\"'
        self.fb_username = self.fb_username.lstrip(chars_to_remove).rstrip(chars_to_remove)
        self.fb_password = self.fb_password.lstrip(chars_to_remove).rstrip(chars_to_remove)

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


class AddNewMusicEntityCommand(CommandAbs):
    def __init__(self, args, parser=None):
        super().__init__()
        self.config = AddNewMusicEntityCommandConfig(args, parser=parser)
        self.data = None
        self.header = None

    @staticmethod
    def create_parser(subparsers):
        parser = subparsers.add_parser(
            CommandType.ADD_NEW_MUSIC_ENTITY.name,
            help="Add new mixes to listen." "Example: --src_file /tmp/file1",
        )
        parser.add_argument('--src_file', type=str)
        parser.set_defaults(func=AddNewMusicEntityCommand.execute)
        parser.add_argument('--duplicate-detection',
                            action='store_true',
                            default=True,
                            help='Whether to detect and not add duplicate items',
                            required=False)
        parser.add_argument('--fbpwd',
                            help='Facebook password',
                            required=True)
        parser.add_argument('--fbuser',
                            help='Facebook username',
                            required=True)

    @staticmethod
    def execute(args, parser=None):
        command = AddNewMusicEntityCommand(args)
        command.run()

    def run(self):
        LOG.info(f"Starting to add new music entities. \n Config: {str(self.config)}")
        config_reader: ParserConfigReader = ParserConfigReader.read_from_file(filename=self.config.parser_conf_json,
                                                                              obj_data_class=ParserConfig,
                                                                              config_type=GenericLineParserConfig)
        LOG.info("Read project config: %s", pformat(config_reader.config))
        parser = MusicEntityInputFileParser(config_reader)
        parsed_objs = parser.parse(self.config.src_file)

        self.header = list(parser.extended_config.fields.by_sheet_name.keys())
        if self.config.operation_mode == OperationMode.GSHEET:
            col_indices_by_fields: Dict[str, int] = self.config.gsheet_wrapper.get_column_indices_of_header()
        else:
            col_indices_by_fields: Dict[str, int] = {col_name: idx for idx, col_name in enumerate(self.header)}

        if self.config.operation_mode == OperationMode.GSHEET and self.config.duplicate_detection:
            LOG.info("Trying to detect duplicates...")
            rows = self.config.gsheet_wrapper.read_data_by_header(ROWS_TO_FETCH, skip_header_row=True)
            LOG.debug("Fetched data from sheet: %s", rows)
            objs_from_sheet = DataConverter.convert_rows_to_data(rows, parser.extended_config.fields,
                                                                 col_indices_by_fields)
            parsed_objs = self.filter_duplicates(objs_from_sheet, parsed_objs)

        facebook = Facebook(self.config)
        content_providers = [Youtube(), facebook, Beatport(), SoundCloud()]
        urls_to_match = [m for cp in content_providers for m in cp.url_matchers()]
        facebook.urls_to_match = urls_to_match
        music_entity_creator = MusicEntityCreator(content_providers)
        music_entities = music_entity_creator.create_music_entities(parsed_objs)
        self.data = DataConverter.convert_data_to_rows(music_entities, parser.extended_config.fields, col_indices_by_fields)

        if not self.header:
            raise ValueError("Header is empty")

        if not self.data:
            raise ValueError("Data is empty")

        BasicResultPrinter.print_table(self.data, self.header)
        if self.config.operation_mode == OperationMode.GSHEET:
            LOG.info("Updating Google sheet with data...")
            self.update_gsheet(parser, col_indices_by_fields)
        elif self.config.operation_mode == OperationMode.DRY_RUN:
            LOG.info("[DRY-RUN] Would add the following rows to Google Sheets: ")
            LOG.info(self.data)
        LOG.info("Finished adding new music entities")

    def update_gsheet(self, parser, col_indices_by_fields):
        # TODO add back later
        # self.config.gsheet_wrapper.write_data_to_new_rows(self.header, self.data, clear_range=False)
        pass

    @staticmethod
    def filter_duplicates(objs_from_sheet: List[p.ParsedMusicEntity],
                          parsed_objs):
        existing_titles = set([obj.title for obj in objs_from_sheet])
        existing_links = set([obj.link_1 for obj in objs_from_sheet])
        existing_links.update([obj.link_2 for obj in objs_from_sheet])
        existing_links.update([obj.link_3 for obj in objs_from_sheet])

        filtered = []
        num_dupes_by_title = 0
        num_dupes_by_link = 0
        for obj in parsed_objs:
            if obj.title in existing_titles:
                LOG.debug("Detected duplicate by title: '%s'", obj.title)
                num_dupes_by_title += 1
            elif obj.link_1 in existing_links:
                num_dupes_by_link += 1
                LOG.debug("Detected duplicate by link1: '%s'", obj.link_1)
            elif obj.link_2 in existing_links:
                num_dupes_by_link += 1
                LOG.debug("Detected duplicate by link2: '%s'", obj.link_2)
            elif obj.link_3 in existing_links:
                num_dupes_by_link += 1
                LOG.debug("Detected duplicate by link3: '%s'", obj.link_3)
            else:
                filtered.append(obj)

        LOG.info("Found %d duplicates by title and %d duplicates by link", num_dupes_by_title, num_dupes_by_link)
        return filtered


class DataConverter:
    TITLE_MAX_LENGTH = 50
    LINK_MAX_LENGTH = 20
    row_stats = None

    @classmethod
    def convert_data_to_rows(cls, music_entities: List[MusicEntity],
                             fields_obj: Fields,
                             col_indices_by_sheet_name: Dict[str, int]) -> List[List[str]]:
        sheet_list_of_rows: List[List[str]] = []
        field_names = [field.name for field in fields_obj.fields]
        cls.row_stats: RowStats = RowStats(field_names)
        for entity in music_entities:
            row, values_by_fields = DataConverter._convert_parsed_entity(entity, fields_obj, col_indices_by_sheet_name)
            DataConverter.update_row_stats(values_by_fields)
            sheet_list_of_rows.append(row)
        cls.row_stats.print_stats()
        return sheet_list_of_rows

    @classmethod
    def _convert_parsed_entity(cls, entity: MusicEntity,
                               fields_obj: Fields,
                               col_indices_by_sheet_name: Dict[str, int]) -> p.ParsedMusicEntity:
        no_of_fields = len(fields_obj.fields)
        row: List[str] = [""] * no_of_fields
        values_by_fields: Dict[str, str] = {}
        for field in fields_obj.fields:
            col_idx = col_indices_by_sheet_name[field.entity_field.name_in_sheet]
            # TODO Here, link should also be read from MusicEntity
            obj_value = Fields.safe_get_attr(entity.data, field.name)
            row[col_idx] = obj_value
            values_by_fields[field.name] = obj_value
        return row, values_by_fields

    @classmethod
    def update_row_stats(cls, values_by_fields):
        cls.row_stats.update(values_by_fields)

    @classmethod
    def convert_rows_to_data(cls, rows: List[List[str]],
                             fields_obj: Fields,
                             col_indices_by_sheet_name: Dict[str, int]) -> List[p.ParsedMusicEntity]:
        res = []
        for row in rows:
            matches = {}
            for f in fields_obj.fields:
                f_sheet_name = f.entity_field.name_in_sheet
                col_idx = col_indices_by_sheet_name[f_sheet_name]
                # GSheet returns shorter rows for empty cells
                if len(row) - 1 < col_idx:
                    matches[f.name] = ""
                else:
                    matches[f.name] = row[col_idx]
            obj = fields_obj.create_object_by_matches(obj_type=p.ParsedMusicEntity, matches=matches)
            res.append(obj)
        return res
