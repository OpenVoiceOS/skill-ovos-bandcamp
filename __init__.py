from py_bandcamp import BandCamper

from mycroft.skills.core import intent_handler, IntentBuilder, \
    intent_file_handler
from mycroft_jarbas_utils.skills.audio import AudioSkill
from mycroft.util.log import LOG
from os import listdir
import csv
import json
from os.path import join, dirname, exists
from mycroft.util.parse import fuzzy_match

__author__ = 'jarbas'


class BandCampSkill(AudioSkill):
    def __init__(self):
        self.named_urls = {}
        self.backend_preference = ["chromecast", "mopidy", "mpv", "vlc",
                                   "mplayer"]
        super(BandCampSkill, self).__init__()
        self.add_filter("music")
        self.settings.set_callback(self.get_playlists_from_file)
        self.band_camp = BandCamper()
        if "max_stream_number" not in self.settings:
            self.settings["max_stream_number"] = 5

    def create_settings_meta(self):
        if "named_urls" not in self.settings:
            self.settings["named_urls"] = join(dirname(__file__),
                                                    "named_urls")
        meta = {
            "name": "BandCamp Skill",
            "skillMetadata": {
                  "sections": [
                      {
                          "name": "Audio Configuration",
                          "fields": [
                              {
                                "type": "text",
                                "name": "default_backend",
                                "value": "vlc",
                                "label": "default_backend"
                              }
                          ]
                      },
                      {
                          "name": "Playlist Configuration",
                          "fields": [
                              {
                                  "type": "label",
                                  "label": "the files in this directory will be read to create aliases and playlists in this skill, the files must end in '.value' and be valid csv, with content ' song name, band camp url ', 'play filename' will play any of the links inside, 'play song name' will play that song name "
                              },
                              {
                                "type": "text",
                                "name": "named_urls",
                                "value": self.settings["named_urls"],
                                "label": "named_urls"
                              }
                            ]
                        }
                      ]
                }
        }
        settings_path = join(self._dir, "settingsmeta.json")
        if not exists(settings_path):
            with open(settings_path, "w") as f:
                f.write(json.dumps(meta))

    def translate_named_playlists(self, name, delim=None):
        delim = delim or ','
        result = {}
        if not name.endswith(".value"):
            name += ".value"

        try:
            with open(join(self.settings["playlist_files"], name)) as f:
                reader = csv.reader(f, delimiter=delim)
                for row in reader:
                    # skip blank or comment lines
                    if not row or row[0].startswith("#"):
                        continue
                    if len(row) != 2:
                        continue
                    if row[0] not in result.keys():
                        result[row[0].rstrip().lstrip()] = []
                    result[row[0]].append(row[1].rstrip().lstrip())
            return result
        except Exception as e:
            self.log.error(str(e))
            return {}

    def get_playlists_from_file(self):
        # read configured radio stations
        stations = {}

        styles = listdir(self.settings["playlist_files"])
        for style in styles:
            name = style.replace(".value", "")
            if name not in stations:
                stations[name] = []
            style_stations = self.translate_named_playlists(style)
            for station_name in style_stations:
                if station_name not in stations:
                    stations[station_name] = style_stations[station_name]
                else:
                    stations[station_name] += style_stations[station_name]
                stations[name] += style_stations[station_name]

        return stations

    def initialize(self):
        self.get_playlists_from_file()
        for named_url in self.named_urls:
            self.register_vocabulary("named_url", named_url)

    @intent_handler(IntentBuilder("BandCampNamedUrlPlay").require(
        "bandcamp").require("play").require("named_url"))
    def handle_named_play(self, message):
        named_url = message.data.get("named_url")
        urls = self.named_urls[named_url]
        self.bandcamp_play(urls=urls)

    @intent_handler(IntentBuilder("BandCampPlay").require(
        "bandcamp").one_of("search", "play"))
    def handle_play_song_intent(self, message):
        # use adapt if band camp is included in the utterance
        # use the utterance remainder as query
        title = message.utterance_remainder()
        self.bandcamp_play(title)

    @intent_handler(IntentBuilder("BandCampSearch")
                    .require("bandcamp").require("search")
                    .at_least_one("artist", "album", "tag", "track"))
    def handle_search_song_intent(self, message):
        # use adapt if band camp is included in the utterance
        # use the utterance remainder as query
        title = message.utterance_remainder()
        urls = []
        i = 0
        if "tag" in message.data:
            for item in self.band_camp.search_tag(title):
                LOG.info(str(item))
                try:
                    urls.append(item["url"])
                    i += 1
                    if i > int(self.settings["max_stream_number"]):
                        break
                except:
                    pass
        elif "album" in message.data:
            for item in self.band_camp.search_albums(title):
                LOG.info(str(item))
                try:
                    urls.append(item["url"])
                    i += 1
                    if i > int(self.settings["max_stream_number"]):
                        break
                except:
                    pass
        elif "artist" in message.data:
            for item in self.band_camp.search_artists(title):
                LOG.info(str(item))
                try:
                    urls.append(item["url"])
                    i += 1
                    if i > int(self.settings["max_stream_number"]):
                        break
                except:
                    pass
        elif "track" in message.data:
            for item in self.band_camp.search_tracks(title):
                LOG.info(str(item))
                try:
                    urls.append(item["url"])
                    i += 1
                    if i > int(self.settings["max_stream_number"]):
                        break
                except:
                    pass
        self.bandcamp_play(urls=urls)

    @intent_file_handler("bandcamp.intent")
    def handle_play_song_padatious_intent(self, message):
        # handle a more generic play command and extract name with padatious
        title = message.data.get("music")
        # fuzzy match with playlists
        best_score = 0
        best_name = ""
        for name in self.named_urls:
            score = fuzzy_match(title, name)
            if score > best_score:
                best_score = score
                best_name = name
        if best_score > 0.7:
            # we have a named list that matches
            urls = self.named_urls[best_name]
            self.bandcamp_play(urls=urls)
        self.bandcamp_play(title)

    def bandcamp_search(self, title):
        streams = []
        self.log.info("Searching Bandcamp for " + title)
        for item in self.band_camp.search(title):
            LOG.info(str(item))
            try:
                streams.append(item["url"])
            except:
                continue
        self.log.info("Bandcamp streams:" + str(streams))
        return streams

    def bandcamp_play(self, title=None, urls=None):
        # were urls provided ?
        urls = urls or []
        if isinstance(urls, basestring):
            urls = [urls]
        # was a search requested ?
        if title is not None:
            self.speak_dialog("searching.bandcamp", {"music": title})
            urls = self.bandcamp_search(title)
        # do we have urls to play ?
        playlist = []
        if len(urls):
            for url in urls:
                if "bandcamp" in url:
                    playlist += self.band_camp.get_streams(url)
                else:
                    playlist.append(url)
            self.play(playlist)
        else:
            raise AssertionError("no bandcamp urls to play")


def create_skill():
    return BandCampSkill()
