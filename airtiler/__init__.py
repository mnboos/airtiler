import json
import argparse
import time
import sys
import os
import overpy
from pygeotile.tile import Tile
from pygeotile.point import Point
import requests
import secrets
import shapely.geometry as geometry
import numpy as np
from PIL import Image, ImageDraw
import shutil
import random


IMAGE_WIDTH = 256


query_template = """
/* TMS {tile} */
[out:json][timeout:50];
( 
  relation["building"]({bbox});
  //node["building"]({bbox});
  way["building"]({bbox});
);
//out geom;
(._;>;);
out body;
"""


def tiles_from_bbox(bbox, zoom_level):
    """
     * Returns all tiles for the specified bounding box
    """

    if isinstance(bbox, dict):
        point_min = Point.from_latitude_longitude(latitude=bbox['tl'], longitude=bbox['tr'])
        point_max = Point.from_latitude_longitude(latitude=bbox['bl'], longitude=bbox['br'])
    elif isinstance(bbox, list):
        point_min = Point.from_latitude_longitude(latitude=bbox[1], longitude=bbox[0])
        point_max = Point.from_latitude_longitude(latitude=bbox[3], longitude=bbox[2])
    else:
        raise RuntimeError("bbox must bei either a dict or a list")
    tile_min = Tile.for_point(point_min, zoom_level)
    tile_max = Tile.for_point(point_max, zoom_level)
    tiles = []
    for x in range(tile_min.tms_x, tile_max.tms_x + 1):
        for y in range(tile_min.tms_y, tile_max.tms_y + 1):
            tiles.append(Tile.from_tms(tms_x=x, tms_y=y, zoom=zoom_level))
    return tiles


def osm_downloader(bbox_name, bbox, zoom_level, output_directory):
    api = overpy.Overpass()

    if not os.path.isdir(output_directory):
        print("Creating folder: {}".format(output_directory))
        os.makedirs(output_directory)
    else:
        print("Downloading to folder: {}".format(output_directory))

    tiles_path = os.path.join(output_directory, 'tiles.txt')
    output_directory = os.path.join(output_directory, str(zoom_level))
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)

    tiles = tiles_from_bbox(bbox=bbox, zoom_level=zoom_level)
    response = requests.get("https://dev.virtualearth.net/REST/V1/Imagery/Metadata/Aerial?key={key}"
                            .format(key=secrets.BING_KEY))
    data = response.json()

    tile_url_template = data['resourceSets'][0]['resources'][0]['imageUrl']
    subdomain = data['resourceSets'][0]['resources'][0]['imageUrlSubdomains'][0]

    loaded_tiles = []
    if os.path.isfile(tiles_path):
        with open(tiles_path, 'r', encoding="utf-8") as f:
            lines = f.readlines()
            loaded_tiles = list(map(lambda l: l[:-1], lines))  # remove '\n'

    all_downloaded = True
    nr_tiles = len(tiles)
    for i, t in enumerate(tiles):
        print("{} @ zoom {}: {:.1f}% (Tile {}/{}) -> {}".format(bbox_name, zoom_level, 100/nr_tiles*i, i+1, nr_tiles, t.tms))
        tms_x, tms_y = t.tms
        tile_name = "{z}_{x}_{y}".format(z=zoom_level, x=tms_x, y=tms_y)
        if tile_name in loaded_tiles:
            continue

        sys.stdout.flush()
        all_downloaded = False
        minx, maxy = t.bounds[0].pixels(zoom_level)
        maxx, miny = t.bounds[1].pixels(zoom_level)
        b = []
        b.extend(t.bounds[0].latitude_longitude)
        b.extend(t.bounds[1].latitude_longitude)
        url = tile_url_template.format(subdomain=subdomain, quadkey=t.quad_tree)
        query = query_template.format(bbox="{},{},{},{}".format(*b), tile=t.tms)
        # print(url)
        # print(query)
        res = api.query(query)
        mask = np.zeros((IMAGE_WIDTH, IMAGE_WIDTH), dtype=np.uint8)
        for way in res.ways:
            points = []
            for node in way.nodes:
                p = Point(float(node.lat), float(node.lon))
                px = p.pixels(zoom=zoom_level)
                points.append((px[0]-minx, px[1]-miny))

            try:
                poly = geometry.Polygon(points)
                tile_rect = geometry.box(0, 0, IMAGE_WIDTH, IMAGE_WIDTH)
                poly = poly.intersection(tile_rect)
            except:
                # print("Intersection failed for polygon and rectangle: poly='{}', box='{}'".format(poly, tile_rect))
                continue
            _update_mask(mask, [poly])

        if res.ways and mask.max():
            file_name = "{}.tif".format(tile_name)
            mask_path = os.path.join(output_directory, file_name)
            img_path = os.path.join(output_directory, file_name+'f')
            Image.fromarray(mask).save(mask_path)
            if not os.path.isfile(img_path):
                response = requests.get(url, stream=True)
                response.raw.decode_content = True
                with open(img_path, 'wb') as file:
                    shutil.copyfileobj(response.raw, file)
                del response
        else:
            print("Tile is empty...")
        with open(tiles_path, 'a') as f:
            f.write("{}\n".format(tile_name))
    return all_downloaded


def _update_mask(mask, polygons, separate_instances=False):
    """
     * The first polygon is the exterior ring. All others are treated as interior rings and will just invert
       the corresponding area of the mask.
    :param separate_instances:
    :param mask:
    :param polygons:
    :return:
    """
    for i, p in enumerate(polygons):
        if isinstance(p, geometry.MultiPolygon):
            _update_mask(mask, p.geoms, True)
            continue
        elif not isinstance(p, geometry.Polygon):
            continue
        outline = Image.fromarray(np.zeros(mask.shape, dtype=np.uint8))
        fill = Image.fromarray(np.zeros(mask.shape, dtype=np.uint8))
        ImageDraw.Draw(outline).polygon(p.exterior.coords, fill=0, outline=255)
        ImageDraw.Draw(fill).polygon(p.exterior.coords, fill=255, outline=0)
        polygons = np.array(outline, dtype=np.uint8)
        fillings = np.array(fill, dtype=np.uint8)
        polygon_area = np.nonzero(polygons)
        if separate_instances:
            mask[polygon_area] ^= 255
        else:
            mask[polygon_area] = 255
        mask[np.nonzero(fillings)] ^= 255


def download(config: dict) -> bool:
    if "boundingboxes" not in config:
        raise RuntimeError("No 'boundingboxes' were specified in the config.")

    bboxes = config['boundingboxes']
    cities = list(bboxes.keys())
    random.shuffle(cities)

    options = config.get("options", {})
    gloabl_zoom_levels = options.get("zoom_levels", [])

    output_directory = options.get("target_dir", ".")
    if not os.path.isabs(output_directory):
        output_directory = os.path.join(os.getcwd(), output_directory)
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)
    assert os.path.isdir(output_directory)

    all_downloaded = True
    for bbox_name in cities:
        print("Processing '{}'...".format(bbox_name))
        bbox = bboxes[bbox_name]

        zoom_levels = gloabl_zoom_levels
        if isinstance(bbox, dict):
            if 'zoom_levels' in bbox:
                zoom_levels = bbox['zoom_levels']

        if not zoom_levels:
            raise RuntimeError("Neither the config nor the bounding box '{}' have any zoom_levels specified.")

        for z in zoom_levels:
            complete = osm_downloader(bbox_name=bbox_name,
                                      bbox=bbox,
                                      zoom_level=z,
                                      output_directory=os.path.join(output_directory, bbox_name))
            if not complete:
                all_downloaded = False
    return all_downloaded


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', type=str, help="Path to the configuration file", required=True)
    args = parser.parse_args()

    if not os.path.isfile(args.config):
        raise FileNotFoundError("Config file does not exist")

    with open(args.config, 'r') as f:
        config = json.load(f)

    run = True
    while run:
        try:
            downloads_complete = download(config)
            if downloads_complete:
                print("{} - All downloads complete!".format(time.ctime()))
            run = not downloads_complete
        except KeyboardInterrupt:
            run = False
        except overpy.exception.OverpassTooManyRequests:
            print("Waiting 2s for overpass...")
            time.sleep(2)
        except Exception as e:
            print("Error occured: " + str(e))
            raise e
