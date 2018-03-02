from airtiler import Airtiler
import json
import os

empty_config = """
{
  "options": {
    "target_dir": "./output",
    "zoom_levels": [18, 19],
    "separate_instances": false
  },
  "boundingboxes": {
    "empty": [11, 43, 10, 43],
    "single_building": [8.8183594613,47.2228679539,8.819253978,47.2234162581]
  }
}
"""


def test_airtiler():
    config = json.loads(empty_config)
    Airtiler(os.environ.get("BING_KEY", "")).process(config)
