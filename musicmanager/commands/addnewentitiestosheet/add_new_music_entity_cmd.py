import logging
import os
from enum import Enum
from pprint import pformat
from typing import List, Dict

from googleapiwrapper.google_sheet import GSheetOptions, GSheetWrapper
from pythoncommons.file_parser.parser_config_reader import GenericLineParserConfig, ParserConfigReader
from pythoncommons.file_utils import FindResultType, FileUtils
from pythoncommons.project_utils import SimpleProjectUtils
from pythoncommons.result_printer import BasicResultPrinter

import musicmanager.commands.addnewentitiestosheet.parser as p
from musicmanager.commands.addnewentitiestosheet.config import ParserConfig, Fields
from musicmanager.commands.addnewentitiestosheet.music_entity_creator import MusicEntityCreator, MusicEntity
from musicmanager.commands.addnewentitiestosheet.parser import MusicEntityInputFileParser
from musicmanager.commands_common import CommandType, CommandAbs
from musicmanager.constants import LocalDirs
from musicmanager.contentprovider.beatport import Beatport
from musicmanager.contentprovider.common import JavaScriptRenderer, JSRenderer
from musicmanager.contentprovider.facebook import Facebook, FacebookLinkParser, FacebookSelenium
from musicmanager.contentprovider.mixcloud import Mixcloud
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
        self.js_renderer: JavaScriptRenderer = self._choose_js_renderer(args)
        self._validate(args, parser)
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
            parent_dir="music-entity-parser"
        )
        self.parser_conf_json = os.path.join(parser_config_dir, "parserconfig.json")
        self._determine_input_files(args)

        # Sanitize Facebook login data
        chars_to_remove = '\'\"'
        self.fb_username = self.fb_username.lstrip(chars_to_remove).rstrip(chars_to_remove)
        self.fb_password = self.fb_password.lstrip(chars_to_remove).rstrip(chars_to_remove)

    def _determine_input_files(self, args):
        self.always_use_project_input_files = args.use_project_input_files
        self.src_dir = None
        self.src_files = []

        if not hasattr(args, "src_dir") and not args.src_dir and \
                not hasattr(args, "src_file") and not args.src_file:
            raise ValueError("Either 'src_dir' or 'src_file' should be specified!")

        if hasattr(args, "src_dir") and args.src_dir:
            self.src_dir = args.src_dir
            LOG.info("Using specified source directory: %s", self.src_dir)
        elif self.always_use_project_input_files:
            self.src_dir = SimpleProjectUtils.get_project_dir(
                basedir=LocalDirs.REPO_ROOT_DIR,
                dir_to_find="input_files",
                find_result_type=FindResultType.DIRS,
                parent_dir="music-entity-parser"
            )

        if hasattr(args, "src_file") and args.src_file:
            self.src_files = [args.src_file]

        if self.src_dir:
            found_files = FileUtils.find_files(self.src_dir, regex=".*.txt", single_level=False, full_path_result=True)
            LOG.debug(
                "Found files in patches output dir: %s",found_files,
            )
            self.src_files.extend(found_files)

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
            f"Source files: {self.src_files}\n"
        )

    @staticmethod
    def _choose_js_renderer(args) -> JavaScriptRenderer:
        if hasattr(args, 'use_requests_html_for_js') and args.use_requests_html_for_js:
            return JavaScriptRenderer.REQUESTS_HTML
        return JavaScriptRenderer.SELENIUM


class AddNewMusicEntityCommand(CommandAbs):
    def __init__(self, args, parser=None):
        super().__init__()
        self.config = AddNewMusicEntityCommandConfig(args, parser=parser)
        self.rows = None
        self.header = None

    @staticmethod
    def create_parser(subparsers):
        parser = subparsers.add_parser(
            CommandType.ADD_NEW_MUSIC_ENTITY.name,
            help="Add new mixes to listen." "Example: --src_file /tmp/file1",
        )
        parser.add_argument('--src-file', type=str)
        parser.add_argument('--src-dir', type=str)
        parser.add_argument('--use-project-input-files',
                            action='store_true',
                            default=False,
                            help='Whether to always use project input files',
                            required=False
                            )
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
        parser.add_argument('--use-requests-html-for-js',
                            action='store_true',
                            default=False,
                            help='Whether to use requests-html library for JS rendering. Otherwise, Selenium will be used.',
                            required=False
                            )

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
        col_indices_by_fields = self._init_header_and_columns(parser)

        parsed_objs = []
        self.rows = []
        for src_file in self.config.src_files:
            parsed_objs.extend(parser.parse(src_file))

        if self.config.operation_mode == OperationMode.GSHEET and self.config.duplicate_detection:
            LOG.info("Trying to detect duplicates...")
            rows = self.config.gsheet_wrapper.read_data_by_header(ROWS_TO_FETCH, skip_header_row=True)
            LOG.debug("Fetched data from sheet: %s", rows)
            objs_from_sheet = DataConverter.convert_rows_to_data(rows, parser.extended_config.fields, col_indices_by_fields)
            parsed_objs = self.filter_duplicates(objs_from_sheet, parsed_objs)

        music_entity_creator = self._create_music_entity_creator()
        music_entities = music_entity_creator.create_music_entities(parsed_objs)

        self.rows = DataConverter.convert_data_to_rows(music_entities, parser.extended_config.fields, col_indices_by_fields)
        self._update_google_sheet(col_indices_by_fields, parser)

    def _update_google_sheet(self, col_indices_by_fields, parser):
        if not self.header:
            raise ValueError("Header is empty")
        if not self.rows:
            raise ValueError("No data to processs (rows)!")
        BasicResultPrinter.print_table(self.rows, self.header)
        if self.config.operation_mode == OperationMode.GSHEET:
            LOG.info("Updating Google sheet with data...")
            self.update_gsheet(parser, col_indices_by_fields)
        elif self.config.operation_mode == OperationMode.DRY_RUN:
            LOG.info("[DRY-RUN] Would add the following rows to Google Sheets: ")
            LOG.info(self.rows)
        LOG.info("Finished adding new music entities")

    def _init_header_and_columns(self, parser):
        self.header = list(parser.extended_config.fields.by_sheet_name.keys())
        if self.config.operation_mode == OperationMode.GSHEET:
            col_indices_by_fields: Dict[str, int] = self.config.gsheet_wrapper.get_column_indices_of_header()
        else:
            col_indices_by_fields: Dict[str, int] = {col_name: idx for idx, col_name in enumerate(self.header)}
        return col_indices_by_fields

    def _create_music_entity_creator(self):
        content_provider_classes = [Youtube, Facebook, Beatport, SoundCloud, Mixcloud]
        urls_to_match = [m for cp in content_provider_classes for m in cp.url_matchers()]
        fb_link_parser = FacebookLinkParser(urls_to_match)
        fb_selenium = FacebookSelenium(self.config, fb_link_parser)
        js_renderer = JSRenderer(self.config.js_renderer, fb_selenium)
        facebook = Facebook(self.config, js_renderer, fb_selenium, fb_link_parser)

        content_providers = [Youtube(), facebook, Beatport(), SoundCloud(), Mixcloud()]
        music_entity_creator = MusicEntityCreator(content_providers)
        return music_entity_creator

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
