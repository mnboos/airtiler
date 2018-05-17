#!/usr/bin/env python3

import json
import argparse
import time
import sys
import os
import overpy
from typing import Tuple, Iterable
from pygeotile.tile import Tile
from pygeotile.point import Point
import requests
import shapely.geometry as geometry
import numpy as np
from PIL import Image, ImageDraw
import shutil
import random

query_template = """
[out:json][timeout:50];
( 
  relation[{tag}]({bbox});
  way[{tag}]({bbox});
);
//out geom;
(._;>;);
out body;
"""


def first(iterable):
    if iterable:
        return iterable[0]
    return None


class Airtiler:
    def __init__(self, image_width=256, bing_key=None):
        self._image_width = image_width
        self._bing_key = bing_key
        self._tile_rect = geometry.box(0, 0, image_width, image_width)

    @staticmethod
    def _tiles_from_bbox(bbox, zoom_level):
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

    def _process_bbox(self, bbox_name: str, bbox: Iterable, zoom_level: int, output_directory: str,
                      separate_instances: bool, tags: Iterable[str]) -> bool:
        if not os.path.isdir(output_directory):
            print("Creating folder: {}".format(output_directory))
            os.makedirs(output_directory)
        else:
            print("Downloading to folder: {}".format(output_directory))

        tiles_path = os.path.join(output_directory, 'tiles.txt')
        output_directory = os.path.join(output_directory, str(zoom_level))
        if not os.path.isdir(output_directory):
            os.makedirs(output_directory)

        tiles = self._tiles_from_bbox(bbox=bbox, zoom_level=zoom_level)

        loaded_tiles = []
        if os.path.isfile(tiles_path):
            with open(tiles_path, 'r', encoding="utf-8") as f:
                lines = f.readlines()
                loaded_tiles = list(map(lambda l: l[:-1], lines))  # remove '\n'

        all_downloaded = True
        nr_tiles = len(tiles)
        if tiles:
            subdomain, tile_url_template = self._get_bing_data()
            bing_url = None
            for i, tile in enumerate(tiles):
                print("{} @ zoom {}: {:.1f}% (Tile {}/{}) -> {}".format(bbox_name, zoom_level, 100 / nr_tiles * i, i + 1,
                                                                        nr_tiles, tile.tms))
                tms_x, tms_y = tile.tms
                tile_name = "{z}_{x}_{y}".format(z=zoom_level, x=tms_x, y=tms_y)
                if tile_name in loaded_tiles:
                    continue

                if tile_url_template and subdomain:
                    bing_url = tile_url_template.format(subdomain=subdomain, quadkey=tile.quad_tree)

                min_lat, min_lon = tile.bounds[0].latitude_longitude
                max_lat, max_lon = tile.bounds[1].latitude_longitude
                all_downloaded = self.download_bbox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat,
                                                    output_directory=output_directory, file_name=tile_name,
                                                    separate_instances=separate_instances, bing_url=bing_url, tags=tags)

                with open(tiles_path, 'a') as f:
                    f.write("{}\n".format(tile_name))
        return all_downloaded

    def _get_bing_data(self) -> Tuple:
        if not self._bing_key:
            return None, None

        response = requests.get("https://dev.virtualearth.net/REST/V1/Imagery/Metadata/Aerial?key={key}"
                                .format(key=self._bing_key))
        data = response.json()
        resource_set = self._get(data.get('resourceSets', []), 0, {})
        resource = self._get(resource_set.get('resources', []), 0, {})
        subdomain = self._get(resource.get('imageUrlSubdomains', []), 0, None)
        image_url = resource.get('imageUrl', None)
        return subdomain, image_url

    @staticmethod
    def _get(coll, index, default):
        return coll[index] if len(coll) > index else default

    highway_width = {
        "motorway": 8,
        "motorway_link": 8,
        "trunk": 8,
        "trunk_link": 8,
        "primary": 8,
        "primary_link": 8,
        "secondary": 6,
        "secondary_link": 6,
        "tertiary": 5,
        "tertiary_link": 5,
        "unclassified": 5,
        "residential": 5,
        "service": 0,
        "footway": 0,
        "steps": 0,
        "track": 0,
        "path": 0,
        "cycleway": 0,
        "elevator": 0
    }

    def _get_masks_by_tag(self, tags, min_lon, min_lat, max_lon, max_lat, separate_instances, verbose):
        offset_lat = max_lat - min_lat
        offset_lon = max_lon - min_lon
        pixels_per_lat = self._image_width / offset_lat
        pixels_per_lon = self._image_width / offset_lon
        bbox = "{},{},{},{}".format(min_lat, min_lon, max_lat, max_lon)
        mask_by_tag = {}
        for tag in tags:
            if "=" in tag:
                attr, value = tag.split("=")
                query_tag = "\"{}\"=\"{}\"".format(attr, value)
                tag = value
            else:
                query_tag = "\"{}\"".format(tag)
            query = query_template.format(bbox=bbox, tag=query_tag)
            api = overpy.Overpass()
            res = api.query(query)
            mask = np.zeros((self._image_width, self._image_width), dtype=np.uint8)
            handled_way_ids = []
            for rel in res.relations:
                outer_points = []
                inner_point_lists = []
                for mem in rel.members:
                    print(mem)
                    way = first(list(filter(lambda n: n.id == mem.ref, res.ways)))
                    if way:
                        handled_way_ids.append(way.id)
                        current_points = []
                        for node in way.nodes:
                            x = pixels_per_lon * (float(node.lon) - min_lon)
                            y = pixels_per_lat * (float(node.lat) - max_lat) * -1
                            current_points.append((x, y))
                        if mem.role == "outer":
                            outer_points.extend(current_points)
                        else:
                            inner_point_lists.append(current_points)
                if outer_points:
                    if inner_point_lists:
                        poly = geometry.Polygon(outer_points, inner_point_lists)
                    else:
                        poly = geometry.Polygon(outer_points)
                    self._process_polygon(mask, poly, separate_instances, verbose)

            for way in res.ways:
                if way.id in handled_way_ids:
                    continue
                points = []
                for node in way.nodes:
                    x = pixels_per_lon * (float(node.lon) - min_lon)
                    y = pixels_per_lat * (float(node.lat) - max_lat) * -1
                    points.append((x, y))
                poly = None
                try:
                    if "highway" in way.tags:
                        hw_type = way.tags["highway"]
                        is_tunnel = "tunnel" in way.tags
                        if is_tunnel:
                            continue
                        if hw_type in self.highway_width:
                            width = self.highway_width[hw_type]
                            poly = geometry.LineString(points).buffer(width)
                        else:
                            print("Unknown highway type: ", hw_type)
                    else:
                        poly = geometry.Polygon(points)
                except:
                    continue
                self._process_polygon(mask, poly, separate_instances, verbose)
            mask_by_tag[tag] = mask
        return mask_by_tag

    def _process_polygon(self, mask, poly, separate_instances, verbose=0):
        if poly:
            if verbose:
                print(poly.wkt)
            if not poly.is_valid:
                poly = poly.buffer(0)
            poly = poly.intersection(self._tile_rect)
            if verbose:
                print(poly.wkt)
            self._update_mask(mask, [poly], separate_instances=separate_instances)

    def download_bbox(self, min_lon, min_lat, max_lon, max_lat, output_directory, file_name, separate_instances=False,
                      bing_url=None, tags=None, verbose=0):
        if not os.path.isdir(output_directory):
            os.makedirs(output_directory)

        if not tags:
            tags = ['building']

        masks_by_tag = self._get_masks_by_tag(tags, min_lon, min_lat, max_lon, max_lat, separate_instances, verbose)
        any_mask_written = False
        for tag in masks_by_tag:
            mask = masks_by_tag[tag]
            if mask.max():
                any_mask_written = True
                mask_path = os.path.join(output_directory, "{name}_{tag}.tif".format(name=file_name, tag=tag))
                Image.fromarray(mask).save(mask_path)

        if any_mask_written:
            img_path = os.path.join(output_directory, "{}.tiff".format(file_name))
            img_exists = os.path.isfile(img_path)
            if bing_url and not img_exists:
                self._download_imagery(bing_url, img_path)
        else:
            print("Tile is empty...")
        return True

    @staticmethod
    def _download_imagery(bing_url, img_path):
        response = requests.get(bing_url, stream=True)
        response.raw.decode_content = True
        with open(img_path, 'wb') as file:
            shutil.copyfileobj(response.raw, file)
        del response

    def _update_mask(self, mask: np.ndarray, polygons: Iterable, separate_instances: bool = False) -> None:
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
                self._update_mask(mask=mask, polygons=p.geoms, separate_instances=True)
                continue
            elif not isinstance(p, geometry.Polygon):
                continue
            poly_area = Image.fromarray(np.zeros(mask.shape, dtype=np.uint8))
            holes = Image.fromarray(np.zeros(mask.shape, dtype=np.uint8))
            outline_color = 0 if separate_instances else 255
            ImageDraw.Draw(poly_area).polygon(p.exterior.coords, fill=255, outline=outline_color)
            for h in p.interiors:
                ImageDraw.Draw(holes).polygon(h.coords, fill=255, outline=255)
            mask[np.nonzero(np.array(poly_area, dtype=np.uint8))] = 255
            mask[np.nonzero(np.array(holes, dtype=np.uint8))] = 0

    def _process_internal(self, config: dict) -> bool:
        """
         * Processes the config. Throw
        :param config:
        :return:
        """

        if "boundingboxes" not in config:
            raise RuntimeError("No 'boundingboxes' were specified in the config.")

        bboxes = config['boundingboxes']
        cities = list(bboxes.keys())
        random.shuffle(cities)

        options = config.get("options", {})
        gloabl_zoom_levels = options.get("zoom_levels", [])
        separate_instances = options.get("separate_instances", False)

        query = config.get("query", {})
        tags = query.get("tags", [])

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
                complete = self._process_bbox(bbox_name=bbox_name,
                                              bbox=bbox,
                                              zoom_level=z,
                                              output_directory=os.path.join(output_directory, bbox_name),
                                              separate_instances=separate_instances,
                                              tags=tags)
                if not complete:
                    all_downloaded = False
        return all_downloaded

    def process(self, config) -> None:
        run = True
        while run:
            try:
                downloads_complete = self._process_internal(config)
                if downloads_complete:
                    print("{} - All downloads complete!".format(time.ctime()))
                run = not downloads_complete
            except KeyboardInterrupt:
                run = False
            except overpy.exception.OverpassTooManyRequests:
                print("OverpassTooManyRequests: Waiting 2s...")
                time.sleep(2)
            except Exception as e:
                print("Error occured: " + str(e))
                raise e


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', type=str, help="Path to the configuration file", required=True)
    parser.add_argument('-k', '--bing-access-token', type=str, help="Access key to the Bing REST API", required=True)
    args = parser.parse_args()

    if not os.path.isfile(args.config):
        raise FileNotFoundError("Config file does not exist")

    with open(args.config, 'r') as f:
        config = json.load(f)

    airtiler = Airtiler(bing_key=args.bing_access_token)
    airtiler.process(config)


if __name__ == "__main__":
    main()
