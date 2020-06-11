from py_bandcamp import BandCamper
from mycroft.util.parse import match_one, fuzzy_match
from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel
from tempfile import gettempdir
from os.path import join, isfile
import requests
from mycroft.messagebus import Message
from mycroft.skills.core import intent_file_handler
import distutils.spawn
import random

# not sure this is from this skill, but damn those logs are annoying
import logging
logging.getLogger("chardet.charsetprober").setLevel(logging.CRITICAL)


class BandCampSkill(CommonPlaySkill):
    def __init__(self):
        super(BandCampSkill, self).__init__()
        if "force_local" not in self.settings:
            self.settings["force_local"] = True
        if "force_vlc" not in self.settings:
            self.settings["force_vlc"] = False
        if "download" not in self.settings:
            self.settings["download"] = True
        if "shuffle" not in self.settings:
            self.settings["shuffle"] = True
        if "num_results" not in self.settings:
            # used for artist (TODO) and genre search
            # track plays single music
            # album plays full album  (TODO)
            self.settings["num_results"] = 3

    def parse_search(self, utterance):
        """
        parse query type, this logic is more or less provider agnostic
        """

        # TODO {track/album} by {artist}
        # TODO {track} from {album}
        # TODO {track_number} track from {album}

        remainder = utterance
        replaces = []
        search_type = "generic"
        explicit = False
        if self.voc_match(utterance, "bandcamp"):
            # bandcamp requested explicitly
            k = self.lang + "bandcamp"
            replaces += self.voc_match_cache[k]
            explicit = True
        if self.voc_match(utterance, "AudioBackend"):
            # remove audio backend request from phrase
            k = self.lang + "AudioBackend"
            replaces += self.voc_match_cache[k]
        if self.voc_match(utterance, "artist"):
            search_type = "artist"
            k = self.lang + "artist"
            replaces += self.voc_match_cache[k]
        elif self.voc_match(utterance, "track"):
            search_type = "track"
            k = self.lang + "track"
            replaces += self.voc_match_cache[k]
        elif self.voc_match(utterance, "album"):
            search_type = "album"
            k = self.lang + "album"
            replaces += self.voc_match_cache[k]
        elif self.voc_match(utterance, "tag"):
            search_type = "tag"
            k = self.lang + "tag"
            replaces += self.voc_match_cache[k]
            # validate tag
            tag = utterance.replace(" ", "-").lower().strip()
            if tag not in BandCamper.tags():
                search_type = "generic"
        elif self.voc_match(utterance, "tag_names"):
            search_type = "tag"
            # validate tag
            tag = utterance.replace(" ", "-").lower().strip()
            if tag not in BandCamper.tags():
                search_type = "generic"

        replaces = sorted(replaces, key=len, reverse=True)
        for r in replaces:
            remainder = remainder.replace(r, "").strip()
        return search_type, explicit, remainder

    def xtract_and_score(self, match, phrase, explicit=False):
        """ Score each match and extract real streams
         This logic is bandcamp specific
         """
        # extend timeout for each match we are scoring
        self.bus.emit(Message('play:query.response',
                              {"phrase": phrase,
                               "searching": True,
                               "skill_id": self.skill_id}))

        # extract streams
        try:
            # TODO scrap full playlists for artist / album  searches
            match["stream"] = BandCamper.get_stream_url(match["url"])
        except Exception as e:
            self.log.error(e)
            return None

        # Get match_type and base_score
        match_type = CPSMatchLevel.GENERIC
        score = 0.5
        if match.get("name") and not match.get("artist"):
            match["artist"] = match.pop("name")
        if match["type"] == "artist":
            match_type = CPSMatchLevel.ARTIST
            if match.get("artist"):
                score = fuzzy_match(phrase, match["artist"])
        elif match["type"] == "track":
            match_type = CPSMatchLevel.TITLE
            if match.get("track_name"):
                score = fuzzy_match(phrase, match["track_name"])
        elif match["type"] == "album":
            match_type = CPSMatchLevel.TITLE
            if match.get("album_name"):
                score = fuzzy_match(phrase, match["album_name"])
        elif match["type"] == "tag":
            match_type = CPSMatchLevel.CATEGORY
            score = 0.6

        # score modifiers
        if match.get("artist"):
            new_score = fuzzy_match(phrase, match["artist"])
            if new_score >= score:
                if match["type"] != "artist":
                    match_type = CPSMatchLevel.MULTI_KEY
                else:
                    match_type = CPSMatchLevel.ARTIST
                score = new_score
            else:
                score += new_score * 0.5
        elif match.get("track_name"):
            new_score = fuzzy_match(phrase, match["track_name"])
            if new_score >= score:
                if match["type"] != "track":
                    match_type = CPSMatchLevel.MULTI_KEY
                else:
                    match_type = CPSMatchLevel.TITLE
                score = new_score
            else:
                score += new_score * 0.5
        elif match.get("album_name"):
            new_score = fuzzy_match(phrase, match["album_name"])
            if new_score >= score:
                if match["type"] != "album":
                    match_type = CPSMatchLevel.MULTI_KEY
                else:
                    match_type = CPSMatchLevel.TITLE
                score = new_score
            else:
                score += new_score * 0.5

        if len(match.get("tags", [])):
            for t in match["tags"]:
                tag_score = fuzzy_match(phrase, t)
                if tag_score > score:
                    match_type = CPSMatchLevel.CATEGORY
                    score = tag_score
                else:
                    score += tag_score * 0.3

        if len(match.get("related_tags", [])):
            for tag in match["related_tags"]:
                new_score = tag["score"]
                if new_score > score:
                    match_type = CPSMatchLevel.CATEGORY
                    score = new_score
                else:
                    score += new_score * 0.3

        # If the confidence is high enough return an exact match
        if score >= 0.9 or explicit:
            match_type = CPSMatchLevel.EXACT

        if score >= 0.5:
            return (phrase, match_type, match)
        # if low confidence return None
        else:
            return None

    def CPS_match_query_phrase(self, phrase):
        original = phrase
        search_type, explicit, phrase = self.parse_search(phrase)

        if search_type == "generic":
            for match in BandCamper.search(phrase):
                data = self.xtract_and_score(match, original, explicit)
                if data:
                    return data
        elif search_type == "artist":
            for match in BandCamper.search_artists(phrase):
                data = self.xtract_and_score(match, original, explicit)
                if data:
                    # TODO extract playlist
                    return data
        elif search_type == "album":
            for match in BandCamper.search_albums(phrase):
                data = self.xtract_and_score(match, original, explicit)
                if data:
                    # TODO extract playlist
                    return data
        elif search_type == "track":
            for match in BandCamper.search_tracks(phrase):
                data = self.xtract_and_score(match, original, explicit)
                if data:
                    return data
        elif search_type == "tag":
            # extend timeout
            self.bus.emit(Message('play:query.response',
                                  {"phrase": original,
                                   "searching": True,
                                   "skill_id": self.skill_id}))
            # pages do not need to be scrapped, full json data available
            matches = list(BandCamper.search_tag(phrase))[:self.settings["num_results"]]
            if len(matches):
                match = {
                    "playlist": [m["audio_url"]['mp3-128'] for m in matches],
                    "tracks": matches
                }
                return (phrase, CPSMatchLevel.CATEGORY, match)
        return None

    def CPS_start(self, phrase, data):
        self.log.debug("Bandcamp data: " + str(data))
        playlist = data.get("playlist") or [data['stream']]

        if self.settings["shuffle"]:
            random.shuffle(playlist)

        # check if vlc installed
        # TODO mplayer
        if distutils.spawn.find_executable("vlc") is None:
            self.settings["force_vlc"] = False
            self.settings["force_local"] = True

        # select audio backend
        utterance = None
        if self.settings["force_vlc"]:
            utterance = "vlc"
        elif self.settings["force_local"]:
            utterance = "local"

        if self.settings["download"] or self.settings["force_local"]:
            # NOTE for some reason vlc is failing to play the extracted
            # streams, vlc is also an optional system requirement,
            # as workaround download to tempfile
            for idx, url in enumerate(playlist):
                path = join(gettempdir(), str(hash(url))[1:] + ".mp3")
                if not isfile(path):
                    data = requests.get(url).content
                    with open(path, "wb") as f:
                        f.write(data)
                playlist[idx] = path
                if idx == 0:
                    self.CPS_play(path, utterance=utterance)

        if len(playlist) > 1:
            self.audioservice.queue(playlist[1:])

    @intent_file_handler("bandcamp.intent")
    def handle_search_bandcamp_intent(self, message):
        """ handles bandcamp searches that dont start with "play" which
        means they would miss the CommonPlay framework invocation """
        title = message.data.get("music")
        self.speak_dialog("searching.bandcamp", {"music": title})
        match = self.CPS_match_query_phrase(title)
        if match is not None:
            self.CPS_start(title, match[2])
        else:
            self.speak_dialog("play.error")

def create_skill():
    return BandCampSkill()
