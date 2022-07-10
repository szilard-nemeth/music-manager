import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pprint import pformat
from typing import List, Dict, Any

from googleapiwrapper.google_sheet import GSheetOptions, GSheetWrapper
from pythoncommons.file_parser.parser_config_reader import GenericLineParserConfig, ParserConfigReader
from pythoncommons.file_utils import FindResultType, FileUtils
from pythoncommons.project_utils import SimpleProjectUtils
from pythoncommons.result_printer import BasicResultPrinter

import musicmanager.commands.addnewentitiestosheet.parser as p
from musicmanager.commands.addnewentitiestosheet.config import ParserConfig, Fields, Sheet
from musicmanager.commands.addnewentitiestosheet.music_entity_creator import MusicEntityCreator, GroupedMusicEntity, \
    MusicEntityType
from musicmanager.commands.addnewentitiestosheet.parser import MusicEntityInputFileParser
from musicmanager.commands_common import CommandType, CommandAbs
from musicmanager.constants import LocalDirs
from musicmanager.contentprovider.beatport import Beatport
from musicmanager.contentprovider.common import JavaScriptRenderer, JSRenderer, HtmlParser
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


@dataclass
class GSheetUpdate:
    sheet: Sheet
    entity_type: MusicEntityType
    gsheet_wrapper: GSheetWrapper
    header: List[str]
    col_indices_by_fields: Dict[str, int]
    operation_mode: OperationMode
    rows: List[Any] = field(default_factory=list)
    data_from_sheet: List[List[str]] = None
    fields_obj: Fields = None

    @property
    def spreadsheet(self):
        return self.gsheet_wrapper.options.spreadsheet

    @property
    def worksheet(self) -> str:
        if not self.gsheet_wrapper.options.single_worksheet_mode:
            raise ValueError("Sheet with name '{}' is not in single worksheet mode!".format(
                self.gsheet_wrapper.options.spreadsheet))
        return self.gsheet_wrapper.options.worksheets[0]

    def fetch_data_from_sheet(self):
        if not self.operation_mode == OperationMode.GSHEET:
            self.data_from_sheet = []
            return self.data_from_sheet

        if not self.data_from_sheet:
            self.data_from_sheet = self.gsheet_wrapper.read_data_by_header(ROWS_TO_FETCH, skip_header_row=True)
            sheet_ref = self.spreadsheet + "/" + self.worksheet
            LOG.debug("Fetched data from sheet '%s': %s", sheet_ref, self.data_from_sheet)
        else:
            LOG.warning("Data from sheet is already fetched")
        return self.data_from_sheet


class AddNewMusicEntityCommandConfig:
    def __init__(self, args, parser=None):
        self.fb_password = args.fbpwd
        self.fb_username = args.fbuser
        self.fb_redirect_link_limit = args.fb_redirect_link_limit
        self.js_renderer: JavaScriptRenderer = self._choose_js_renderer(args)
        self._validate(args, parser)
        self.duplicate_detection = args.duplicate_detection

    def _validate(self, args, parser):
        if args.gsheet and args.gsheet_client_secret is None:
            parser.error("--gsheet requires the following mandatory arguments: \n"
                         "--gsheet-client-secret.")
        self.operation_mode = self._validate_operation_mode(args)

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
        self.updates = List[GSheetUpdate]

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
        parser.add_argument('--fb-redirect-link-limit',
                            type=int,
                            default=10,
                            help='The number of maximum Facebook redirect links to handle per post. Default is 10.',
                            required=False
                            )

    @staticmethod
    def execute(args, parser=None):
        command = AddNewMusicEntityCommand(args)
        command.run(args)

    def run(self, args):
        LOG.info(f"Starting to add new music entities. \n Config: {str(self.config)}")
        config_reader: ParserConfigReader = ParserConfigReader.read_from_file(filename=self.config.parser_conf_json,
                                                                              obj_data_class=ParserConfig,
                                                                              config_type=GenericLineParserConfig)
        LOG.info("Read project config: %s", pformat(config_reader.config))
        parser = MusicEntityInputFileParser(config_reader)
        sheets = parser.extended_config.parser_settings.sheet_settings.sheets
        # TODO Verify if ONLY ONE sheet object is defined per entity type!
        # TODO Verify if sheet object is defined only once (no duplicate sheet configs)
        gsheet_updates: Dict[MusicEntityType, GSheetUpdate] = self._init_gsheet_updates(sheets, parser.extended_config.fields, args.gsheet_client_secret)

        parsed_objs = []
        for src_file in self.config.src_files:
            parsed_objs.extend(parser.parse(src_file))

        music_entity_creator = self._create_music_entity_creator()
        music_entities: List[GroupedMusicEntity] = music_entity_creator.create_music_entities(parsed_objs)

        for me in music_entities:
            me.finalize_and_validate()
        # TODO Run duplicate detection on parsed_objs OR music_entities before proceeding

        entity_types = [e for e in MusicEntityType]
        music_entities_by_type: Dict[MusicEntityType, List[GroupedMusicEntity]] = self._group_music_entities_by_type(music_entities, entity_types)

        unknown_entities = music_entities_by_type[MusicEntityType.UNKNOWN]
        if unknown_entities:
            LOG.error("Unknown entities: %s", unknown_entities)
        not_found_entities = music_entities_by_type[MusicEntityType.NOT_FOUND]
        if not_found_entities:
            LOG.error("Not found entities: %s", not_found_entities)

        for update in gsheet_updates.values():
            LOG.info("Trying to detect duplicates (sheet vs. objects)...")
            update.fetch_data_from_sheet()
            objs_from_sheet = DataConverter.convert_rows_to_data(update, update.fields_obj)
            entities: List[GroupedMusicEntity] = music_entities_by_type[update.entity_type]
            if self.config.duplicate_detection:
                entities = self.filter_duplicates(objs_from_sheet, entities)

            update.rows = DataConverter.convert_data_to_rows(entities,
                                                             update.fields_obj,
                                                             update.col_indices_by_fields)
            self._update_google_sheet(update)

    def _update_google_sheet(self, update):
        if not update.header:
            raise ValueError("Header is empty")
        if not update.rows:
            raise ValueError("No data to processs (rows)!")
        BasicResultPrinter.print_table(update.rows, update.header)
        if self.config.operation_mode == OperationMode.GSHEET:
            LOG.info("Updating Google sheet with data...")
            self.update_gsheet(update)
        elif self.config.operation_mode == OperationMode.DRY_RUN:
            LOG.info("[DRY-RUN] Would add the following rows to Google Sheets: ")
            LOG.info(update.rows)
        LOG.info("Finished adding new music entities")

    def _init_gsheet_updates(self, sheets, fields: Fields, gsheet_client_secret: str):
        gsheet_updates = {}
        for sheet in sheets:
            gsheet_options = GSheetOptions(gsheet_client_secret,
                                           sheet.spreadsheet_name,
                                           sheet.worksheet_name)
            gsheet_wrapper = GSheetWrapper(gsheet_options)

            field_names = sheet.fields
            if self.config.operation_mode == OperationMode.GSHEET:
                # TODO Validate col_indices_by_fields vs. field_names: col_indices_by_fields should contain all from field_names
                col_indices_by_fields: Dict[str, int] = gsheet_wrapper.get_column_indices_of_header()
            else:
                col_indices_by_fields: Dict[str, int] = {col_name: idx for idx, col_name in enumerate(field_names)}
            # TODO Is the header correct? --> VALIDATE: Length of sheet header ('col_indices_by_fields') should be the same as field_names
            if len(field_names) != len(col_indices_by_fields.keys()):
                raise ValueError("Length of fields vs. header of Google sheet is different "
                                 "(# of fields: {} vs. # of header fields: {}. "
                                 "Fields: {}, header: {}"
                                 .format(len(field_names), len(col_indices_by_fields), field_names, col_indices_by_fields.keys()))
            update = GSheetUpdate(sheet=sheet,
                                  entity_type=sheet.entity_type,
                                  gsheet_wrapper=gsheet_wrapper,
                                  header=field_names,
                                  operation_mode=self.config.operation_mode,
                                  col_indices_by_fields=col_indices_by_fields)
            update.fields_obj = fields.get_view_by_field_names(update.sheet.fields)
            gsheet_updates[sheet.entity_type] = update

        return gsheet_updates

    def _create_music_entity_creator(self):
        content_provider_classes = [Youtube, Facebook, Beatport, SoundCloud, Mixcloud]
        urls_to_match = [m for cp in content_provider_classes for m in cp.url_matchers()]
        fb_link_parser = FacebookLinkParser(urls_to_match, self.config.fb_redirect_link_limit)
        fb_selenium = FacebookSelenium(self.config, fb_link_parser)
        js_renderer = JSRenderer(self.config.js_renderer, fb_selenium)
        # TODO dirty hack
        HtmlParser.js_renderer = js_renderer
        facebook = Facebook(self.config, js_renderer, fb_selenium, fb_link_parser)

        content_providers = [Youtube(), facebook, Beatport(), SoundCloud(), Mixcloud()]
        music_entity_creator = MusicEntityCreator(content_providers)
        return music_entity_creator

    def update_gsheet(self, update: GSheetUpdate):
        # TODO add back later
        # self.config.gsheet_wrapper.write_data_to_new_rows(self.header, self.data, clear_range=False)
        pass

    @staticmethod
    def filter_duplicates(objs_from_sheet: List[p.ParsedMusicEntity],
                          entities: List[GroupedMusicEntity]) -> List[GroupedMusicEntity]:
        if not objs_from_sheet:
            return entities

        titles_from_sheet = set([obj.title for obj in objs_from_sheet])
        links_from_sheet = set([l for obj in objs_from_sheet for l in MusicEntityCreator.get_links_of_parsed_objs(obj)])

        filtered: List[GroupedMusicEntity] = []
        duplicate_entities_by_title = []
        duplicate_entities_by_link = []
        for entity in entities:
            if entity.title in titles_from_sheet:
                LOG.debug("Detected duplicate by title: '%s'", entity.title)
                duplicate_entities_by_title.append(entity)
                continue

            intersection = entity.links.intersection(links_from_sheet)
            if intersection:
                LOG.debug("Detected duplicate by links: '%s'", intersection)
                duplicate_entities_by_link.append(entity)
            else:
                filtered.append(entity)

        LOG.info("Found %d duplicates by title and %d duplicates by link",
                 len(duplicate_entities_by_title), len(duplicate_entities_by_link))
        return filtered

    @staticmethod
    def _group_music_entities_by_type(music_entities: List[GroupedMusicEntity], entity_types: List[MusicEntityType]) -> Dict[MusicEntityType, List[GroupedMusicEntity]]:
        res = {}
        for et in entity_types:
            res[et] = list(filter(lambda x: x.entity_type == et, music_entities))

        remainders = list(filter(lambda x: x.entity_type not in entity_types or
                                           x.entity_type == MusicEntityType.UNKNOWN, music_entities))

        # TODO raise exception if soundcloud Music entity type is implemented
        # if remainders:
        #     raise ValueError("Some music entities are having unknown types: {}".format(remainders))
        return res


class DataConverter:
    TITLE_MAX_LENGTH = 50
    LINK_MAX_LENGTH = 20
    row_stats = None

    @classmethod
    def convert_data_to_rows(cls, music_entities: List[GroupedMusicEntity],
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
    def _convert_parsed_entity(cls, entity: GroupedMusicEntity,
                               fields_obj: Fields,
                               col_indices_by_sheet_name: Dict[str, int]) -> p.ParsedMusicEntity:
        no_of_fields = len(fields_obj.fields)
        row: List[str] = [""] * no_of_fields
        values_by_fields: Dict[str, str] = {}
        for field in fields_obj.fields:
            col_idx = col_indices_by_sheet_name[field.entity_field.name_in_sheet]
            # TODO Here, link should also be read from GroupedMusicEntity
            obj_value = Fields.safe_get_attr(entity.data, field.name)
            row[col_idx] = obj_value
            values_by_fields[field.name] = obj_value
        return row, values_by_fields

    @classmethod
    def update_row_stats(cls, values_by_fields):
        cls.row_stats.update(values_by_fields)

    @classmethod
    def convert_rows_to_data(cls, gsheet_update: GSheetUpdate,
                             fields_obj: Fields) -> List[p.ParsedMusicEntity]:
        res = []
        for row in gsheet_update.data_from_sheet:
            matches = {}
            for f in fields_obj.fields:
                f_sheet_name = f.entity_field.name_in_sheet
                col_idx = gsheet_update.col_indices_by_fields[f_sheet_name]
                # GSheet returns shorter rows for empty cells
                if len(row) - 1 < col_idx:
                    matches[f.name] = ""
                else:
                    matches[f.name] = row[col_idx]
            obj = fields_obj.create_object_by_matches(obj_type=p.ParsedMusicEntity, matches=matches)
            res.append(obj)
        return res
