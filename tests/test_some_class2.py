import datetime
import logging
import os
import re
import unittest
from typing import Dict
from unittest.mock import patch

from pythoncommons.constants import ExecutionMode
from pythoncommons.file_utils import FileUtils
from pythoncommons.logging_setup import SimpleLoggingSetup
from pythoncommons.project_utils import ProjectUtils, ProjectRootDeterminationStrategy

VALID_CONFIG_FILE = "cdsw_job_config.json"

PROJECT_NAME = "cdsw-config-reader"

LOG = logging.getLogger(__name__)
NETWORK_UTILS_PATCH_PATH = "pythoncommons.network_utils.NetworkUtils.fetch_json"

class CdswConfigReaderTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ProjectUtils.set_root_determine_strategy(ProjectRootDeterminationStrategy.COMMON_FILE)
        ProjectUtils.get_test_output_basedir(PROJECT_NAME)
        cls._setup_logging()

    def setUp(self):
        pass

    def tearDown(self) -> None:
        pass

    @classmethod
    def _setup_logging(cls):
        SimpleLoggingSetup.init_logger(
            project_name="cdsw_config_reader",
            logger_name_prefix="cdswconfigreader",
            execution_mode=ExecutionMode.TEST,
            console_debug=True,
            format_str="%(message)s",
        )

    def test_1(self):
        pass
        # call some production method

        #self.assertIsNotNone(config)
        #self.assertEqual("Reviewsync", config.job_name)

    def test_2(self):
        pass
        # call some production method

        #self.assertIsNotNone(config.runs)
        #self.assertIsNotNone(run)
        #self.assertIsNotNone(run.email_settings)
        #self.assertEqual(run.email_settings.email_body_file_from_command_data, "report-short.html")

    @patch(NETWORK_UTILS_PATCH_PATH)
    def test_with_mocking(self, mock_fetch_json):
        pass
