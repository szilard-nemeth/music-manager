from pythoncommons.file_utils import FileUtils

PROJECT_NAME = "musicmanager"
DEFAULT_FIELD_PREFIX_SEPARATOR = ":"
REPO_ROOT_DIRNAME = "music-manager"


class LocalDirs:
    REPO_ROOT_DIR = FileUtils.find_repo_root_dir(__file__, REPO_ROOT_DIRNAME)


# Symlink names
LATEST_DATA_ZIP_LINK_NAME = "latest-command-data-zip"
