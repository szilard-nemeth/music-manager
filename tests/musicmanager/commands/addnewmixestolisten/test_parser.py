import logging
import os
import sys
import unittest
from typing import List, Set, Tuple

from pythoncommons.file_parser.parser_config_reader import ParserConfigReader, GenericLineParserConfig
from pythoncommons.file_utils import FileUtils, FindResultType
from pythoncommons.object_utils import ObjUtils
from pythoncommons.project_utils import SimpleProjectUtils

from musicmanager.commands.addnewmixestolisten.config import ParserConfig, Fields
from musicmanager.commands.addnewmixestolisten.parser import NewMixesToListenInputFileParser
from musicmanager.constants import LocalDirs

A_REAL_LINK = "https://soundcloud.com/sebabusto/sebastian-busto-moonlight-radio-show-noviembre-2021?in=sebabusto/sets/moonlight-radio-show"

TEXTFILE = "/tmp/pythontest/textfile"

LOG = logging.getLogger(__name__)
CMD_LOG = logging.getLogger(__name__)
REPO_ROOT_DIRNAME = "music-manager"


class NewMixesToListenInputFileParserTest(unittest.TestCase):
    parser_config_dir = None
    repo_root_dir = None
    parsed_obj_dataclass = None

    @classmethod
    def setUpClass(cls):
        cls._setup_logging()
        cls.repo_root_dir = FileUtils.find_repo_root_dir(__file__, REPO_ROOT_DIRNAME)
        cls._setup_dirs()

        cls.parser_config_dir = SimpleProjectUtils.get_project_dir(
            basedir=LocalDirs.REPO_ROOT_DIR,
            dir_to_find="parser_config",
            find_result_type=FindResultType.DIRS,
            parent_dir="mix-listen-parser"
        )
        cls.parser_conf_json = os.path.join(cls.parser_config_dir, "parserconfig.json")

    @classmethod
    def tearDownClass(cls) -> None:
        pass

    def setUp(self):
        self.test_instance = self

    def tearDown(self) -> None:
        pass

    @classmethod
    def _setup_logging(cls):
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
        handler = logging.StreamHandler(stream=sys.stdout)
        CMD_LOG.propagate = False
        CMD_LOG.addHandler(handler)
        handler.setFormatter(logging.Formatter("%(message)s"))

    @classmethod
    def _setup_dirs(cls):
        # TODO
        pass
        # some_dir = SimpleProjectUtils.get_project_dir(
        #         basedir=cls.repo_root_dir, parent_dir=PROJECT_NAME, dir_to_find="commands",
        #         find_result_type=FindResultType.DIRS
        #     )

    # title:"test title" addedat:2022.04.20 listenedat:2022.05.02 tracksearch:yes tracksearchdone:yes lc:2 relisten:yes genre:"progressive house" comment:"test comment__"  https://www.facebook.com/100001272234500/posts/5240658839319805/ link2:http://google.com link3:http://google22.com
    def test_parser_one_word(self):
        self._write_to_file(["oneword"])
        self.read_config_and_parse_input_file()

        self.assertTrue(len(self.parsed_objs) == 1)
        self._assert_field_having_value(self.parsed_objs[0], [("title", "oneword")])

    def test_parser_two_words(self):
        self._write_to_file(["firstword secondword"])
        self.read_config_and_parse_input_file()

        self.assertTrue(len(self.parsed_objs) == 1)
        self._assert_field_having_value(self.parsed_objs[0], [("title", "firstword secondword")])

    def test_parser_title_and_link(self):
        self._write_to_file(["firstword https://google.com"])
        self.read_config_and_parse_input_file()

        self.assertTrue(len(self.parsed_objs) == 1)
        self._assert_field_having_value(self.parsed_objs[0], [("title", "firstword"), ("link_1", "https://google.com")])

    def test_parser_title_and_link_with_prefix(self):
        self._write_to_file(["title:test_title link:https://google.com"])
        self.read_config_and_parse_input_file()

        self.assertTrue(len(self.parsed_objs) == 1)
        self._assert_field_having_value(self.parsed_objs[0], [("title", "test_title"), ("link_1", "https://google.com")])

    def test_parser_parse_from_field(self):
        self._write_to_file([f"from:Someone addedat:05.03 ${A_REAL_LINK}"])
        self.read_config_and_parse_input_file()

        self.assertTrue(len(self.parsed_objs) == 1)
        self._assert_field_having_value(self.parsed_objs[0], [("title", None),
                                                              ("from", "Someone"),
                                                              ("link_1", A_REAL_LINK),
                                                              ("added_at", "05.03")])

    def _assert_field_having_value(self, parsed_obj, fields_with_values: List[Tuple[str, str]]):
        self.assertTrue(isinstance(parsed_obj, self.parsed_obj_dataclass))
        fields_with_values = self._convert_field_names(fields_with_values)
        for f_name, f_val in fields_with_values:
            self.assertEqual(f_val, Fields.safe_get_attr(parsed_obj, f_name),
                             msg="Parsed object: " + str(parsed_obj) + ", field: " + f_name)

        f_names = [f[0] for f in fields_with_values]
        rest_of_the_fields = self.all_field_names.difference(set(f_names))
        ObjUtils.ensure_all_attrs_with_value(parsed_obj, rest_of_the_fields, None)

    @staticmethod
    def _convert_field_names(f_tuples):
        converted_fields = []
        for f_tup in f_tuples:
            converted_key = Fields.convert_dataclass_property_name_to_config_field_name(f_tup[0], lower=True)
            converted_key = Fields._convert_keyword_if_any(converted_key)
            converted_fields.append((converted_key, f_tup[1]))
        return converted_fields

    def read_config_and_parse_input_file(self):
        config_reader: ParserConfigReader = ParserConfigReader.read_from_file(filename=self.parser_conf_json,
                                                                              obj_data_class=ParserConfig,
                                                                              config_type=GenericLineParserConfig)
        parser = NewMixesToListenInputFileParser(config_reader)
        self.parsed_obj_dataclass = NewMixesToListenInputFileParser.ParsedListenToMixRow
        self.all_field_names: Set[str] = set(parser.extended_config.fields.dataclass_fields.keys())
        self.parsed_objs = parser.parse(TEXTFILE)

    @staticmethod
    def _write_to_file(lines: List[str]):
        FileUtils.create_new_empty_file(TEXTFILE)
        FileUtils.write_to_file(TEXTFILE, "\n".join(lines))

