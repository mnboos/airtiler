from airtiler import Airtiler
import json

empty_config = """
{
  "options": {
    "target_dir": "./output",
    "zoom_levels": [18, 19],
    "separate_instances": false
  },
  "boundingboxes": {
    "empty": [11, 43, 10, 43]
  }
}
"""


def test_airtiler():
    config = json.loads(empty_config)
    Airtiler("").process(config)
