from py_bandcamp import BandCamper
from mycroft.util.parse import match_one, fuzzy_match
from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel,\
    CPSTrackStatus
from tempfile import gettempdir
from os.path import join, isfile, dirname
import requests
from mycroft.messagebus import Message
from mycroft.skills.core import intent_file_handler
import distutils.spawn
from time import sleep
import random
from auto_regex import AutoRegex

# not sure this is from this skill, but damn those logs are annoying
import logging

logging.getLogger("chardet.charsetprober").setLevel(logging.CRITICAL)


class BandCampSkill(CommonPlaySkill):
    def __init__(self):
        super(BandCampSkill, self).__init__()
        if "force_local" not in self.settings:
            self.settings["force_local"] = False
        if "force_vlc" not in self.settings:
            self.settings["force_vlc"] = False
        if "force_mplayer" not in self.settings:
            self.settings["force_mplayer"] = False
        if "download" not in self.settings:
            self.settings["download"] = True
        if "shuffle" not in self.settings:
            self.settings["shuffle"] = True
        if "num_results" not in self.settings:
            # used for artist (TODO) and genre search
            # track plays single music
            # album plays full album  (TODO)
            self.settings["num_results"] = 3
        self.regexes = {}

    def initialize(self):
        self._load_rx("track_album")
        self._load_rx("track_artist")
        self._load_rx("track_album_artist")
        self._load_rx("n_album") # track number N from {album}

    def _load_rx(self, regex):
        if regex not in self.regexes:
            path = self.find_resource(regex + '.autoregex', "vocab")
            if path:
                with open(path) as f:
                    rules = f.read().split("\n")
                self.regexes[regex] = [r for r in rules if r.strip()]
        return self.regexes[regex]

    def parse_search(self, utterance):
        """
        parse query type, this logic is more or less provider agnostic
        """
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

        # clean string
        replaces = sorted(replaces, key=len, reverse=True)
        for r in replaces:
            remainder = remainder.replace(r, "").strip()
        data = {"query": remainder}

        # autoregex rules
        for r in self.regexes:
            rx = AutoRegex()
            rx.add_rules(self.regexes[r])
            matches = list(rx.extract(utterance))
            if len(matches):
                search_type = r
                if search_type == "n_album":
                    pass # TODO extract number
                data = {"query": matches[0]["track"]}
                data.update(matches[0])

        return search_type, explicit, data

    def xtract_and_score(self, match, phrase, explicit=False, multi=False):
        """ Score each match and extract real streams
         This logic is bandcamp specific

         match - result from bandcamp
         phrase - original query
         explicit - exact match because bandcamp was requested
         multi - some key already matched (artist/track/album)
         """
        self.extend_timeout(phrase)

        if "audio_url" in match:
            match["stream"] = match.pop("audio_url").pop('mp3-128')
        elif not match.get("stream"):
            try:
                match["stream"] = BandCamper.get_stream_url(match["url"])
            except Exception as e:
                self.log.error(e)
                return None

        # Get match_level and base_score
        match_level = CPSMatchLevel.GENERIC
        score = 0.5
        if match.get("name") and not match.get("artist"):
            match["artist"] = match.pop("name")
        if match["type"] == "artist":
            match_level = CPSMatchLevel.ARTIST
            if match.get("artist"):
                score = fuzzy_match(phrase, match["artist"])
        elif match["type"] == "track":
            match_level = CPSMatchLevel.TITLE
            if match.get("track_name"):
                score = fuzzy_match(phrase, match["track_name"])
        elif match["type"] == "album":
            match_level = CPSMatchLevel.TITLE
            if match.get("album_name"):
                score = fuzzy_match(phrase, match["album_name"])
        elif match["type"] == "tag":
            match_level = CPSMatchLevel.CATEGORY
            score = 0.6

        # score modifiers
        if match.get("artist"):
            new_score = fuzzy_match(phrase, match["artist"])
            if new_score >= score:
                if match["type"] != "artist":
                    match_level = CPSMatchLevel.MULTI_KEY
                else:
                    match_level = CPSMatchLevel.ARTIST
                score = new_score
            else:
                score += new_score * 0.5
        elif match.get("track_name"):
            new_score = fuzzy_match(phrase, match["track_name"])
            if new_score >= score:
                if match["type"] != "track":
                    match_level = CPSMatchLevel.MULTI_KEY
                else:
                    match_level = CPSMatchLevel.TITLE
                score = new_score
            else:
                score += new_score * 0.5
        elif match.get("album_name"):
            new_score = fuzzy_match(phrase, match["album_name"])
            if new_score >= score:
                if match["type"] != "album":
                    match_level = CPSMatchLevel.MULTI_KEY
                else:
                    match_level = CPSMatchLevel.TITLE
                score = new_score
            else:
                score += new_score * 0.5

        if len(match.get("tags", [])):
            for t in match["tags"]:
                tag_score = fuzzy_match(phrase, t)
                if tag_score > score:
                    match_level = CPSMatchLevel.CATEGORY
                    score = tag_score
                else:
                    score += tag_score * 0.3

        if len(match.get("related_tags", [])):
            for tag in match["related_tags"]:
                new_score = tag["score"]
                if new_score > score:
                    match_level = CPSMatchLevel.CATEGORY
                    score = new_score
                else:
                    score += new_score * 0.3

        # If the confidence is high enough return an exact match
        if score >= 0.9 or explicit:
            match_level = CPSMatchLevel.EXACT
        elif multi:
            match_level = CPSMatchLevel.MULTI_KEY

        # add to disambiguation page
        data = match
        data["uri"] = match["stream"]
        data["status"] = CPSTrackStatus.DISAMBIGUATION
        data["score"] = score
        data["match_level"] = match_level
        self.CPS_send_status(**data)

        if score >= 0.5:
            return (phrase, match_level, match)
        # if low confidence return None
        else:
            return None

    def play(self, path, utterance=None, track_data=None):
        track_data = track_data or {}

        artist = track_data.get("artist", "") or \
                 track_data.get("band_name", "") or \
                 track_data.get("name", "") or \
                 track_data.get("title", "")
        track = track_data.get("featured_track_title", "") or \
                track_data.get("track_name", "") or track_data.get("title", "")
        genre = track_data.get("genre", "")
        image = track_data.get("image", "")
        album = track_data.get("album_name", "") or \
                track_data.get("title", "") or track_data.get("name", "")
        self.CPS_send_status(uri=path, artist=artist, track=track, album=album,
                             image=image,  track_length="", current_position=0,
                             genre=genre, playlist_position=0,
                             status=CPSTrackStatus.QUEUED_AUDIOSERVICE)
        self.CPS_play(path, utterance=utterance)

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

    def extend_timeout(self, phrase):
        # extend timeout
        self.bus.emit(Message('play:query.response',
                              {"phrase": phrase,
                               "searching": True,
                               "skill_id": self.skill_id}))

    def CPS_match_query_phrase(self, phrase):
        original = phrase
        search_type, explicit, query_data = self.parse_search(phrase)
        phrase = query_data["query"]

        self.extend_timeout(original) # webscrapping takes a while

        if search_type == "generic":
            for match in BandCamper.search(phrase):
                data = self.xtract_and_score(match, original, explicit)
                if data:
                    return data

        if "track" in search_type:
            for match in BandCamper.search_tracks(phrase):
                multi = False
                if query_data.get("album"):
                    # require album match
                    score = fuzzy_match(query_data["album"].lower(),
                                        match["album_name"].lower())
                    if score < 0.75:
                        continue
                    self.log.debug("album matches track")
                    multi = True
                if query_data.get("artist"):
                    score = fuzzy_match(query_data["artist"].lower(),
                                        match["artist"].lower())
                    if score < 0.85 and not query_data.get("album"):
                        # require artist match if no album match
                        continue
                    self.log.debug("artist matches track")
                    multi = True
                data = self.xtract_and_score(match, original, explicit, multi)
                if data:
                    return data

        if "album" in search_type:
            if query_data.get("album"):
                # album name extracted with regex
                query = query_data["album"]
            else:
                query = phrase

            # TODO check requested track number

            for match in BandCamper.search_albums(query):
                multi = False
                if query_data.get("artist"):
                    # require artist match
                    score = fuzzy_match(query_data["artist"].lower(),
                                        match["artist"].lower())
                    if score < 0.85:
                        continue
                    self.log.debug("artist matches album")
                    multi = True
                data = self.xtract_and_score(match, original, explicit, multi)
                if data:
                    # TODO extract playlist (pybandcamp)
                    return data

        if "artist" in search_type:

            for match in BandCamper.search_artists(phrase):
                self.extend_timeout(original) # this step takes longer
                # because more parsing is needed

                multi = False
                albums = [a["album_name"].lower() for a in match["albums"]]
                if query_data.get("album"):
                    # require album match
                    if len(albums):
                        album, score = match_one(query_data["album"].lower(),
                                            albums)
                        if score < 0.8:
                            continue
                        self.log.debug("album matches artist")
                        idx = albums.index(album)
                        album_url = match["albums"][idx]["url"]
                        match.update(BandCamper.get_stream_data(album_url))
                        multi = True
                    else:
                        continue
                elif query_data.get("track"):
                    # track might also mean album, also check it but dont
                    # require
                    if len(albums):
                        album, score = match_one(query_data["track"].lower(),
                                            albums)
                        if score >= 0.8:
                            self.log.debug("album matches artist")
                            idx = albums.index(album)
                            album_url = match["albums"][idx]["url"]
                            match.update(BandCamper.get_stream_data(album_url))
                            multi = True

                data = self.xtract_and_score(match, original, explicit, multi)
                if data:
                    # TODO extract playlist (pybandcamp)
                    return data

        if search_type == "tag":
            # pages do not need to be scrapped, full json data available at
            # once
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
        tracks = data.get("tracks") or [data]

        if self.settings["shuffle"]:
            # Shuffle two lists with same order
            # Using zip() + * operator + shuffle()
            temp = list(zip(playlist, tracks))
            random.shuffle(temp)
            res1, res2 = zip(*temp)
            playlist = list(res1)
            tracks = list(res2)

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
                    audio_data = requests.get(url).content
                    with open(path, "wb") as f:
                        f.write(audio_data)
                playlist[idx] = path
                if idx == 0:
                    self.play(path, utterance, tracks[idx])
        else:
            self.play(playlist[0], utterance, tracks[0])

        sleep(1)  # TODO wait for track start or queueing will be missed
        for idx, track in enumerate(playlist[1:]):
            self.audioservice.queue(track, utterance=utterance, autoplay=False)
            data = tracks[idx]
            data["uri"] = track
            data["playlist_position"] = idx
            data["status"] = CPSTrackStatus.QUEUED_AUDIOSERVICE
            self.CPS_send_status(**data)


def create_skill():
    return BandCampSkill()
