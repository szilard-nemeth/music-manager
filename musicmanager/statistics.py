# TODO Copied from gdrive2sheet / move to python-commons?
from typing import Dict, List
import logging
LOG = logging.getLogger(__name__)


class RowStats:
    def __init__(self, list_of_fields: List[str], track_unique: List[str] = None):
        self.list_of_fields = list_of_fields
        self.track_unique_values = track_unique
        if not self.track_unique_values:
            self.track_unique_values = []

        self.longest_fields: Dict[str, str] = {field: "" for field in list_of_fields}
        self.unique_values: Dict[str, set] = {}
        self.longest_line = ""

    def update(self, row_dict):
        # Update longest fields dict values if required
        for field_name in self.list_of_fields:
            self._update_field(field_name, self._safe_get_value(row_dict, field_name))

        for field_name in self.track_unique_values:
            if field_name not in self.unique_values:
                self.unique_values[field_name] = set()
            self.unique_values[field_name].add(self._safe_get_value(row_dict, field_name))

        # Store longest line
        sum_length = 0
        for field_name in self.list_of_fields:
            sum_length += len(self._safe_get_value(row_dict, field_name))
        if sum_length > len(self.longest_line):
            self.longest_line = self._safe_join_values(row_dict)

    @staticmethod
    def _safe_get_value(row_dict, field_name):
        val = row_dict[field_name]
        if not val:
            return ""
        return val

    @staticmethod
    def _safe_join_values(row_dict, sep=","):
        vals = [str(val or '') for val in row_dict.values()]
        return sep.join(vals)

    def _update_field(self, field_name, field_value):
        if len(field_value) > len(self.longest_fields[field_name]):
            self.longest_fields[field_name] = field_value

    def print_stats(self):
        LOG.info("Longest line is: '%s' (%d characters)", self.longest_line, len(self.longest_line))
        for field_name in self.track_unique_values:
            self._print(field_name)

        if len(self.unique_values) > 0:
            for field_name, values_set in self.unique_values.items():
                LOG.info("Unique values of field '%s': %s", field_name, ",".join(values_set))

    def _print(self, field_name):
        field_value = self.longest_fields[field_name]
        LOG.info("Longest %s is: '%s' (length: %d characters)", field_name, field_value, len(field_value))