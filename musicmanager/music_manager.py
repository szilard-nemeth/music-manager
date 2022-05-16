#!/usr/bin/python

import argparse
import logging
import os
import time

from pythoncommons.constants import ExecutionMode
from pythoncommons.logging_setup import SimpleLoggingSetupConfig, SimpleLoggingSetup
from pythoncommons.os_utils import OsUtils
from pythoncommons.project_utils import ProjectUtils, ProjectRootDeterminationStrategy

from musicmanager.commands.addnewmixestolisten.add_new_mixes_to_listen_cmd import AddNewMixesToListenCommand
from musicmanager.commands_common import GSheetArguments
from musicmanager.common import MusicManagerEnvVar
from musicmanager.constants import PROJECT_NAME
from musicmanager.music_manager_config import MusicManagerConfig

LOG = logging.getLogger(__name__)

__author__ = 'Szilard Nemeth'


class ArgParser:
    @staticmethod
    def parse_args():
        """This function parses and return arguments passed in"""
        parser = argparse.ArgumentParser()

        # Subparsers
        subparsers = parser.add_subparsers(
            title="subcommands",
            description="valid subcommands",
            help="Available subcommands",
            required=True,
            dest="command",
        )
        AddNewMixesToListenCommand.create_parser(subparsers)

        parser.add_argument('-v', '--verbose',
                            action='store_true',
                            dest='verbose',
                            default=None,
                            required=False,
                            help='More verbose log')

        parser.add_argument(
            "-d",
            "--debug",
            action="store_true",
            dest="debug",
            default=None,
            required=False,
            help="Turn on console debug level logs",
        )

        exclusive_group = parser.add_mutually_exclusive_group(required=True)
        exclusive_group.add_argument('-dr', '--dry-run', action='store_true',
                                     dest='dry_run',
                                     help='Print row updates only to console',
                                     required=False)
        exclusive_group.add_argument('-g', '--gsheet', action='store_true',
                                     dest='gsheet', default=True,
                                     required=False,
                                     help='Export values to Google sheet. '
                                          'Additional gsheet arguments need to be specified!')

        gsheet_group = GSheetArguments.add_gsheet_arguments(parser)
        args = parser.parse_args()

        if args.verbose:
            print("Args: " + str(args))
        return args, parser


class MusicManager:
    def __init__(self, args):
        self.setup_dirs()

    def setup_dirs(self, execution_mode: ExecutionMode = ExecutionMode.PRODUCTION):
        # TODO Copied from yarndevtools
        strategy = None
        if execution_mode == ExecutionMode.PRODUCTION:
            strategy = ProjectRootDeterminationStrategy.SYS_PATH
        elif execution_mode == ExecutionMode.TEST:
            strategy = ProjectRootDeterminationStrategy.COMMON_FILE
        if MusicManagerEnvVar.PROJECT_DETERMINATION_STRATEGY.value in os.environ:
            env_value = OsUtils.get_env_value(MusicManagerEnvVar.PROJECT_DETERMINATION_STRATEGY.value)
            LOG.info("Found specified project root determination strategy from env var: %s", env_value)
            strategy = ProjectRootDeterminationStrategy[env_value.upper()]
        if not strategy:
            raise ValueError("Unknown project root determination strategy!")
        LOG.info("Project root determination strategy is: %s", strategy)
        ProjectUtils.project_root_determine_strategy = strategy
        MusicManagerConfig.PROJECT_OUT_ROOT = ProjectUtils.get_output_basedir(PROJECT_NAME)

    @property
    def get_logs_dir(self):
        return ProjectUtils.get_logs_dir()


if __name__ == '__main__':
    start_time = time.time()

    args, parser = ArgParser.parse_args()
    music_manager = MusicManager(args)

    # Initialize logging
    verbose = True if args.verbose else False
    logging_config: SimpleLoggingSetupConfig = SimpleLoggingSetup.init_logger(
        project_name=PROJECT_NAME,
        logger_name_prefix=PROJECT_NAME,
        execution_mode=ExecutionMode.PRODUCTION,
        console_debug=args.debug,
        postfix=args.command,
        repos=None,
    )
    LOG.info("Logging to files: %s", logging_config.log_file_paths)

    # Call the handler function
    args.func(args, parser=parser)

    end_time = time.time()
    LOG.info("Execution of script took %d seconds", end_time - start_time)
