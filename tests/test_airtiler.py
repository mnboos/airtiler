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

roads_config = """
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
    "roads": [8.5290505109,47.3665699008,8.5317756352,47.3685391392]
  }
}
"""

vineyard_config = """
{
  "options": {
    "target_dir": "./output",
    "zoom_levels": [18],
    "separate_instances": false
  },
  "query": {
    "tags": ["landuse=vineyard"]
  },
  "boundingboxes": {
    "single_building": [8.2101117454,47.3099180991,8.2247029624,47.3191922714]
  }
}
"""


def _cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


IMG_SIZE = 512
key = os.environ.get("BING_KEY", "")


def get_airtiler(set_key=False, image_size=IMG_SIZE):
    k = key if set_key else None
    return Airtiler(bing_key=k, image_width=image_size)


def test_empty_config():
    config = json.loads(empty_config)
    Airtiler(bing_key="").process(config)


def test_single_building_config():
    _cleanup("./output/single_building")
    config = json.loads(single_building_config)
    get_airtiler(set_key=True).process(config)
    images = glob.glob("./output/single_building/**/*.tif*", recursive=True)
    expected_nr_images = 3 if not key else 5  # on travis the bing key is set and therefore the tile can be downloaded
    assert len(images) == expected_nr_images


def test_download_bbox():
    get_airtiler().download_bbox(8.5336971952,47.3625587407,8.5351026728,47.3633799336,
                    output_directory="./output/download_bbox", file_name="single_bbox")
    img = Image.open("./output/download_bbox/single_bbox_building.tif")
    assert img.size == (IMG_SIZE, IMG_SIZE)


def test_download_roads():
    _cleanup("./output/roads")
    config = json.loads(roads_config)
    get_airtiler(set_key=True, image_size=256).process(config)
    img = Image.open("./output/roads/18/18_137282_170333.tiff")
    assert img.size == (256, 256)


def test_download_vineyard_seengen():
    get_airtiler().download_bbox(8.2101117454,47.3099180991,8.2247029624,47.3191922714,
                    output_directory="./output/vineyard", file_name="seengen", tags=["landuse=vineyard"], invert_intersection=False, verbose=0)
    img = Image.open("./output/vineyard/seengen_vineyard.tif")
    assert img.size == (IMG_SIZE, IMG_SIZE)


def test_download_swimming_pool_seengen():
    get_airtiler().download_bbox(8.210252472,47.3158741942,8.2144152604,47.3188490452,
                    output_directory="./output/pool", file_name="seengen", tags=["leisure=swimming_pool"], invert_intersection=False, verbose=0)
    img = Image.open("./output/pool/seengen_swimming_pool.tif")
    assert img.size == (IMG_SIZE, IMG_SIZE)


def test_download_building_with_hole_seengen():
    get_airtiler().download_bbox(8.1930997454,47.3228237375,8.1939634167,47.3234346427,
                    output_directory="./output/building_with_hole", file_name="seengen", tags=["building"], invert_intersection=False, verbose=0)
    img = Image.open("./output/building_with_hole/seengen_building.tif")
    assert img.size == (IMG_SIZE, IMG_SIZE)
