import logging
from abc import ABC, abstractmethod
from enum import Enum

from musicmanager.constants import LATEST_DATA_ZIP_LINK_NAME

LOG = logging.getLogger(__name__)


class CommandAbs(ABC):
    def __init__(self):
        pass

    @staticmethod
    @abstractmethod
    def create_parser(subparsers):
        pass

    @staticmethod
    @abstractmethod
    def execute(args, parser=None):
        pass


class GSheetArguments:
    @staticmethod
    def add_gsheet_arguments(parser):
        # Arguments for Google sheet integration
        gsheet_group = parser.add_argument_group("google-sheet", "Arguments for Google sheet integration")

        gsheet_group.add_argument(
            "--gsheet-client-secret",
            dest="gsheet_client_secret",
            required=False,
            help="Client credentials for accessing Google Sheet API",
        )

        gsheet_group.add_argument(
            "--gsheet-spreadsheet",
            dest="gsheet_spreadsheet",
            required=False,
            help="Name of the Google Sheet spreadsheet",
        )

        gsheet_group.add_argument(
            "--gsheet-worksheet",
            dest="gsheet_worksheet",
            required=False,
            help="Name of the worksheet in the Google Sheet spreadsheet",
        )
        return gsheet_group


class CommandType(Enum):
    ADD_NEW_MUSIC_ENTITY = ("add_new_music_entity", "add-new-music-entity", False)

    def __init__(self, value, output_dir_name, session_based: bool, session_link_name: str = ""):
        self.real_name = value
        self.session_based = session_based
        self.output_dir_name = output_dir_name

        if session_link_name:
            self.session_link_name = session_link_name
        else:
            self.session_link_name = f"latest-session-{value}"

        self.log_link_name = f"latest-log-{value}"
        self.command_data_name = f"latest-command-data-{value}"
        self.command_data_zip_name: str = f"{LATEST_DATA_ZIP_LINK_NAME}-{value}"