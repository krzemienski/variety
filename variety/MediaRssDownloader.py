# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Peter Levi <peterlevi@peterlevi.com>
# This program is free software: you can redistribute it and/or modify it 
# under the terms of the GNU General Public License version 3, as published 
# by the Free Software Foundation.
# 
# This program is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranties of 
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR 
# PURPOSE.  See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along 
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE

import urllib2
import random
import urlparse
import xml.etree.ElementTree as ET

import logging
from variety import Downloader
from variety.Util import Util

logger = logging.getLogger('variety')

random.seed()

MEDIA_NS = "{http://search.yahoo.com/mrss/}"

class MediaRssDownloader(Downloader.Downloader):
    def __init__(self, parent, url):
        super(MediaRssDownloader, self).__init__(parent, "Media RSS", url)
        self.queue = []

    def convert_to_filename(self, url):
        return "mediarss_" + super(MediaRssDownloader, self).convert_to_filename(url)

    @staticmethod
    def fetch(url):
        content = urllib2.urlopen(url, timeout=20).read()
        return ET.fromstring(content)

    @staticmethod
    def is_valid_content(x):
        return x is not None and "url" in x.attrib and (
            Util.is_image(x.attrib["url"]) or
            ("medium" in x.attrib and x.attrib["medium"].lower() == "image") or
            ("type" in x.attrib and x.attrib["type"].lower().startswith("image/"))
        )

    @staticmethod
    def validate(url):
        logger.info("Validating MediaRSS url " + url)
        try:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "http://" + url

            s = MediaRssDownloader.fetch(url)
            walls = [x.attrib["url"] for x in s.findall(".//{0}content".format(MEDIA_NS))
                     if MediaRssDownloader.is_valid_content(x)]
            return len(walls) > 0
        except Exception:
            logger.exception("Error while validating URL, proabably not a MediaRSS feed")
            return False

    def download_one(self):
        logger.info("Downloading an image from MediaRSS, " + self.location)
        logger.info("Queue size: %d" % len(self.queue))

        if not self.queue:
            self.fill_queue()
        if not self.queue:
            logger.info("MediaRSS queue empty after fill")
            return None

        origin_url, image_url = self.queue.pop()
        parse = urlparse.urlparse(origin_url)
        host = parse.netloc if hasattr(parse, "netloc") else "origin"
        return self.save_locally(origin_url, image_url, origin_name=host)

    @staticmethod
    def picasa_hack(feed_url):
        """ Picasa hack - by default Picasa's RSS feeds link to low-resolution images.
        Add special parameter to request the full-resolution instead:"""
        if feed_url.find("://picasaweb.") > 0:
            logger.info("Picasa hack to get full resolution images: add imgmax=d to the feed URL")
            feed_url = feed_url.replace("&imgmax=", "&imgmax_disabled=")
            feed_url += "&imgmax=d"
            logger.info("Final Picasa feed URL: " + feed_url)

        return feed_url

    def fill_queue(self):
        logger.info("MediaRSS URL: " + self.location)
        feed_url = self.location
        feed_url = MediaRssDownloader.picasa_hack(feed_url)

        s = self.fetch(feed_url)

#        try:
#            self.channel_title = s.find("channel/title").text
#        except Exception:
#            self.channel_title = "origin"
#
        for item in s.findall(".//item"):
            try:
                origin_url = item.find("link").text
                group = item.find("{0}group".format(MEDIA_NS))
                content = None
                width = -1
                if group is not None:
                    # find the largest image in the group
                    for c in group.findall("{0}content".format(MEDIA_NS)):
                        try:
                            if MediaRssDownloader.is_valid_content(c):
                                if content is None:
                                    content = c # use the first one, in case we don't find any width info
                                if "width" in c.attrib and int(c.attrib["width"]) > width:
                                    content = c
                                    width = int(c.attrib["width"])
                        except Exception:
                            pass
                else:
                    content = item.find("{0}content".format(MEDIA_NS))

                if MediaRssDownloader.is_valid_content(content):
                    self.process_content(origin_url, content)
            except Exception:
                logger.exception("Could not process an item in the Media RSS feed")

        random.shuffle(self.queue)
        logger.info("MediaRSS queue populated with %d URLs" % len(self.queue))

    def process_content(self, origin_url, content):
        try:
            logger.debug("Checking origin_url " + origin_url)

            if self.parent and origin_url in self.parent.banned:
                logger.debug("In banned, skipping")
                return

            image_file_url = content.attrib["url"]

            if self.is_in_downloaded(image_file_url):
                logger.debug("Already in downloaded")
                return

            if self.is_in_favorites(image_file_url):
                logger.debug("Already in favorites")
                return

            width = None
            height = None
            try:
                width = int(content.attrib["width"])
                height = int(content.attrib["height"])
            except Exception:
                pass

            if self.parent and width and height and not self.parent.size_ok(width, height):
                logger.debug("Small or non-landscape size/resolution")
                return

            logger.debug("Appending to queue %s, %s" % (origin_url, image_file_url))
            self.queue.append((origin_url, image_file_url))
        except Exception:
            logger.exception("Error parsing single MediaRSS image info:")