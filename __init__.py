from os.path import join, dirname

from json_database import JsonStorageXDG
from mycroft.util.parse import fuzzy_match
from ovos_plugin_common_play.ocp import MediaType, \
    PlaybackType
from ovos_utils.parse import fuzzy_match
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill, \
    ocp_search
from py_bandcamp import BandCamper, BandcampAlbum, BandcampTrack, \
    BandcampArtist


class BandCampSkill(OVOSCommonPlaybackSkill):
    def __init__(self):
        super(BandCampSkill, self).__init__()
        self.regexes = {}
        self.supported_media = [MediaType.GENERIC,
                                MediaType.MUSIC]
        self._search_cache = JsonStorageXDG("bandcamp.search.history",
                                            subfolder="common_play")
        self.default_bg = join(dirname(__file__), "ui", "icon.png")
        self.default_image = join(dirname(__file__), "ui", "icon.png")
        self.skill_icon = join(dirname(__file__), "ui", "icon.png")
        if "min_score" not in self.settings:
            self.settings["min_score"] = 40
        if "use_cache" not in self.settings:
            self.settings["use_cache"] = False

    # common play
    @ocp_search()
    def search_bandcamp_artist(self, phrase,
                               media_type=MediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 30
        if media_type == MediaType.MUSIC:
            base_score += 15
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            if self.settings["use_cache"]:
                if "artists" not in self._search_cache:
                    self._search_cache["artists"] = {}
                if phrase not in self._search_cache["artists"]:
                    self._search_cache["artists"][phrase] = []
                else:
                    # cache hit!
                    for r in self._search_cache["artists"][phrase]:
                        yield r
                    return

            # TODO common play support to return full playlists
            #  - artist top tracks
            n = 1  # 1 artist only, best tracks are individual results
            for match in BandCamper.search_artists(phrase):
                n -= 1
                for res in self.bandcamp2cps(match, base_score, phrase):
                    yield res
                    if res["match_confidence"] > 0 and self.settings[
                        "use_cache"]:
                        self._search_cache["artists"][phrase].append(res)
                if n <= 0:
                    break
            if self.settings["use_cache"]:
                self._search_cache.store()
        except:
            pass

    @ocp_search()
    def search_bandcamp_tracks(self, phrase,
                               media_type=MediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 20
        if media_type == MediaType.MUSIC:
            base_score += 10
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            if self.settings["use_cache"]:
                if "tracks" not in self._search_cache:
                    self._search_cache["tracks"] = {}
                if phrase not in self._search_cache["tracks"]:
                    self._search_cache["tracks"][phrase] = []
                else:
                    # cache hit!
                    for r in self._search_cache["tracks"][phrase]:
                        yield r
                    return

            n = 3
            for match in BandCamper.search_tracks(phrase):
                n -= 1
                for res in self.bandcamp2cps(match, base_score, phrase):
                    yield res
                    if res["match_confidence"] > 0 and self.settings[
                        "use_cache"]:
                        self._search_cache["tracks"][phrase].append(res)
                if n <= 0:
                    break
            if self.settings["use_cache"]:
                self._search_cache.store()
        except:
            pass

    @ocp_search()
    def search_bandcamp_album(self, phrase,
                              media_type=MediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 30
        if media_type == MediaType.MUSIC:
            base_score += 20
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            if self.settings["use_cache"]:
                if "albums" not in self._search_cache:
                    self._search_cache["albums"][phrase] = {}
                if phrase not in self._search_cache["albums"][phrase]:
                    self._search_cache["albums"][phrase][phrase] = []
                else:
                    # cache hit!
                    for r in self._search_cache["albums"][phrase]:
                        yield r
                    return

            # TODO common play support to return full playlists
            #  - full album
            n = 1  # 1 album only, tracks are individual results
            for match in BandCamper.search_albums(phrase):
                n -= 1
                for res in self.bandcamp2cps(match, base_score, phrase):
                    yield res
                    if res["match_confidence"] > 0 and self.settings[
                        "use_cache"]:
                        self._search_cache["albums"][phrase].append(res)
                if n <= 0:
                    break
            if self.settings["use_cache"]:
                self._search_cache.store()
        except:
            pass

    def bandcamp2cps(self, match, base_score, phrase):
        urls = []

        if isinstance(match, BandcampArtist):
            artist_name = match.name
            artist_score = fuzzy_match(artist_name, phrase) * 100
            score = base_score + artist_score

            # featured track from featured album -> high confidence
            track = match.featured_track
            if track:
                urls.append(track.url)
                yield {
                    "match_confidence": min(100, score),
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + track.url,
                    "playback": PlaybackType.AUDIO,
                    "image": track.image or match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "title": track.title,
                    "artist": artist_name,
                    "skill_id": self.skill_id
                    # "author": match.name,
                    # "album": match.album.title if match.album else ""
                }
            # todo once playlists are supported return album as single
            #  result and reenable this single track result
            """
            if match.featured_album:
                track = match.featured_album.featured_track
                if track.url not in urls:
                    urls.append(track.url)
                    yield {
                        "match_confidence": min(100, score),
                        "media_type": MediaType.MUSIC,
                        "uri": track.stream,
                        "playback": PlaybackType.AUDIO,
                        "image": track.image or match.image,
                        "bg_image": match.image,
                        "skill_icon": self.skill_icon,
                        "skill_logo": self.skill_logo,
                        "title": track.title,
                        "skill_id": self.skill_id
                        # "author": t.artist.name,
                        # "album": album.title if match.album else ""
                    }
            """

            # todo once playlists are supported return album as single result
            # featured album tracks -> medium confidence
            # NOTE: this is faster than parsing than parsing all albums below
            album = match.featured_album
            for idx, track in enumerate(album.tracks):
                if track.url in urls:
                    continue
                score -= idx  # to preserve ordering
                urls.append(track.url)
                yield {
                    "match_confidence": min(100, score),
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + track.url,
                    "playback": PlaybackType.AUDIO,
                    "image": track.image or album.image or match.image,
                    "bg_image": album.image or match.image,
                    "skill_icon": self.skill_icon,
                    "title": track.title,
                    "artist": artist_name,
                    "skill_id": self.skill_id
                    # "author": t.artist.name,
                    # "album": t.album.title if match.album else ""
                }

            # todo once playlists are supported return albums as single results
            # all albums tracks -> low conf
            for idx, album in enumerate(match.albums):
                score -= idx  # to preserve ordering
                for idx2, track in enumerate(album.tracks):
                    if track.url in urls:
                        continue
                    score -= idx2  # to preserve ordering
                    urls.append(track.url)
                    yield {
                        "match_confidence": min(100, score),
                        "media_type": MediaType.MUSIC,
                        "uri": "bandcamp//" + track.url,
                        "playback": PlaybackType.AUDIO,
                        "image": track.image or album.image or match.image,
                        "bg_image": album.image or match.image,
                        "skill_icon": self.skill_icon,
                        "title": track.title,
                        "skill_id": self.skill_id
                        # "author": t.artist.name,
                        # "album": album.title if match.album else ""
                    }

        if isinstance(match, BandcampAlbum):
            # TODO common play support to return full playlists instead of
            #  individual tracks
            artist_name = match.artist.name
            album_score = fuzzy_match(match.title, phrase) * 100
            artist_score = fuzzy_match(artist_name, phrase) * 80
            album_score = max(album_score, artist_score)

            # featured track -> very high confidence
            if match.featured_track:
                urls.append(match.featured_track.url)

                score = base_score + album_score

                yield {
                    "match_confidence": min(100, score),
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + match.featured_track.url,
                    "playback": PlaybackType.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "artist": artist_name,
                    "skill_icon": self.skill_icon,
                    "title": match.featured_track.title,
                    "skill_id": self.skill_id
                    # "author": match.artist.name,
                    # "album": match.title
                }

            # all albums tracks -> high confidence
            # todo once playlists are supported return album as single result
            for idx, track in enumerate(match.tracks):
                if track.url in urls:
                    continue
                score = base_score + album_score - idx
                yield {
                    "match_confidence": min(100, score),
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + track.url,
                    "playback": PlaybackType.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "title": track.title,
                    "artist": artist_name,
                    "skill_id": self.skill_id
                    # "author": match.artist.name,
                    # "album": match.title
                }

        if isinstance(match, BandcampTrack):
            artist_name = match.artist.name
            track_score = fuzzy_match(match.title, phrase) * 80
            artist_score = fuzzy_match(artist_name, phrase) * 100
            track_score = max(track_score, artist_score)
            score = base_score + track_score

            if match.url not in urls:
                yield {
                    "match_confidence": min(100, score),
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + match.url,
                    "playback": PlaybackType.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "title": match.title,
                    "artist": artist_name,
                    "skill_id": self.skill_id
                    # "author": match.artist.name,
                    # "album": match.album.title if match.album else {}
                }


def create_skill():
    return BandCampSkill()
