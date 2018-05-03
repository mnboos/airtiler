from airtiler import Airtiler
from PIL import Image
import json
import os
import glob
import shutil

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
  "query": {
    "tags": ["highway", "building"]
  },
  "boundingboxes": {
    "single_building": [8.8183594613,47.2228679539,8.819253978,47.2234162581]
  }
}
"""

roads_building_config = """
{
  "options": {
    "target_dir": "./output",
    "zoom_levels": [18],
    "separate_instances": false
  },
  "query": {
    "tags": ["highway"]
  },
  "boundingboxes": {
    "single_building": [8.8183594613,47.2228679539,8.819253978,47.2234162581]
  }
}
"""


def _cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


def test_empty_config():
    config = json.loads(empty_config)
    Airtiler(bing_key="").process(config)


def test_single_building_config():
    _cleanup("./output/single_building")
    config = json.loads(single_building_config)
    key = os.environ.get("BING_KEY", "")
    Airtiler(bing_key=key).process(config)
    images = glob.glob("./output/single_building/**/*.tif*", recursive=True)
    expected_nr_images = 3 if not key else 5  # on travis the bing key is set and therefore the tile can be downloaded
    assert len(images) == expected_nr_images


def test_download_bbox():
    IMG_SIZE = 512
    a = Airtiler(image_width=IMG_SIZE)
    # a.download_bbox(min_lon=8.8132623492, min_lat=47.2236615975, max_lon=8.820407754, max_lat=47.2276689455,
    a.download_bbox(8.5336971952,47.3625587407,8.5351026728,47.3633799336,
                    output_directory="./output/download_bbox", file_name="single_bbox", verbose=1)
    img = Image.open("./output/download_bbox/single_bbox_building.tif")
    assert img.size == (IMG_SIZE, IMG_SIZE)


def test_download_roads():
    IMG_SIZE = 512
    a = Airtiler(image_width=IMG_SIZE)
    a.download_bbox(8.1089472819,47.1770185723,8.110578065,47.1781124768,
                    output_directory="./output/roads", file_name="roads", tags=["highway", "building"], invert_intersection=False)
    img = Image.open("./output/roads/roads_highway.tif")
    assert img.size == (IMG_SIZE, IMG_SIZE)
