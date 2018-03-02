from airtiler import Airtiler
import json
import os
import glob

empty_config = """
{
  "options": {
    "target_dir": "./output",
    "zoom_levels": [18],
    "separate_instances": false
  },
  "boundingboxes": {
    "empty": [11, 43, 10, 43]
  }
}
"""

single_building_config = """
{
  "options": {
    "target_dir": "./output",
    "zoom_levels": [18],
    "separate_instances": false
  },
  "boundingboxes": {
    "single_building": [8.8183594613,47.2228679539,8.819253978,47.2234162581]
  }
}
"""


def test_empty_config():
    config = json.loads(empty_config)
    Airtiler("").process(config)


def test_single_building_config():
    config = json.loads(single_building_config)
    key = os.environ.get("BING_KEY", "")
    Airtiler(key).process(config)
    images = glob.glob("./output/**/*.tif", recursive=True)
    expected_nr_images = 1 if not key else 2  # on travis the bing key is set and therefore the tile can be downloaded
    assert len(images) == expected_nr_images

