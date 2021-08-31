from os.path import join, dirname

from mycroft.util.parse import fuzzy_match
from ovos_utils.parse import fuzzy_match
from ovos_workshop.frameworks.playback import CommonPlayMediaType, \
    CommonPlayPlaybackType
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill, \
    common_play_search
from py_bandcamp import BandCamper, BandcampAlbum, BandcampTrack, \
    BandcampArtist


class BandCampSkill(OVOSCommonPlaybackSkill):
    def __init__(self):
        super(BandCampSkill, self).__init__()
        self.regexes = {}
        self.supported_media = [CommonPlayMediaType.GENERIC,
                                CommonPlayMediaType.MUSIC]
        self._search_cache = {}
        self.default_bg = join(dirname(__file__), "ui", "icon.png")
        self.default_image = join(dirname(__file__), "ui", "icon.png")
        self.skill_logo = join(dirname(__file__), "ui", "icon.png")
        self.skill_icon = join(dirname(__file__), "ui", "icon.png")
        if "min_score" not in self.settings:
            self.settings["min_score"] = 40

    # common play
    @common_play_search()
    def search_bandcamp_artist(self, phrase,
                               media_type=CommonPlayMediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 30
        if media_type == CommonPlayMediaType.MUSIC:
            base_score += 15
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            # TODO common play support to return full playlists
            #  - artist top tracks
            # 1 artist only, best tracks are individual results
            for match in BandCamper.search_artists(phrase):
                return list(self.bandcamp2cps(match, base_score, phrase))
        except:
            pass
        return []

    @common_play_search()
    def search_bandcamp_tracks(self, phrase,
                               media_type=CommonPlayMediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 20
        if media_type == CommonPlayMediaType.MUSIC:
            base_score += 10
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            for match in BandCamper.search_tracks(phrase):
                return list(self.bandcamp2cps(match, base_score, phrase))
        except:
            pass
        return []

    @common_play_search()
    def search_bandcamp_album(self, phrase,
                              media_type=CommonPlayMediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 30
        if media_type == CommonPlayMediaType.MUSIC:
            base_score += 20
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            # TODO common play support to return full playlists
            #  - full album
            # 1 album only, tracks are individual results
            for match in BandCamper.search_albums(phrase):
                return list(self.bandcamp2cps(match, base_score, phrase))
        except:
            pass
        return []

    def bandcamp2cps(self, match, base_score, phrase):
        urls = []

        if isinstance(match, BandcampArtist):
            artist_score = fuzzy_match(match.name, phrase) * 100
            score = base_score + artist_score

            # featured track from featured album -> high confidence
            if match.featured_track:
                track = match.featured_track
                urls.append(track.url)
                yield {
                    "match_confidence": min(100, score),
                    "media_type": CommonPlayMediaType.MUSIC,
                    "uri": track.stream,
                    "playback": CommonPlayPlaybackType.AUDIO,
                    "image": track.image or match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": track.title,
                    "skill_id": self.skill_id
                    # "author": match.name,
                    # "album": match.album.title if match.album else ""
                }
            if match.featured_album:
                track = match.featured_album.featured_track
                urls.append(track.url)
                yield {
                    "match_confidence": min(100, score),
                    "media_type": CommonPlayMediaType.MUSIC,
                    "uri": track.stream,
                    "playback": CommonPlayPlaybackType.AUDIO,
                    "image": track.image or match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": track.title,
                    "skill_id": self.skill_id
                    # "author": t.artist.name,
                    # "album": album.title if match.album else ""
                }

            # featured album tracks -> medium confidence
            for idx, track in enumerate(match.featured_album.tracks):
                if track.url in urls:
                    continue
                score = base_score + artist_score - idx * 5
                urls.append(track.url)
                yield {
                    "match_confidence": min(100, score),
                    "media_type": CommonPlayMediaType.MUSIC,
                    "uri": track.stream,
                    "playback": CommonPlayPlaybackType.AUDIO,
                    "image": track.image or match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": track.title,
                    "skill_id": self.skill_id
                    # "author": t.artist.name,
                    # "album": t.album.title if match.album else ""
                }

            # all albums tracks -> low conf
            for idx, album in enumerate(match.albums):
                for idx2, track in enumerate(album.tracks):
                    if track.url in urls:
                        continue
                    score = base_score + 2 + artist_score - idx - idx2 * 10

                    urls.append(track.url)
                    yield {
                        "match_confidence": min(100, score - 5),
                        "media_type": CommonPlayMediaType.MUSIC,
                        "uri": track.stream,
                        "playback": CommonPlayPlaybackType.AUDIO,
                        "image": track.image or match.image,
                        "bg_image": match.image,
                        "skill_icon": self.skill_icon,
                        "skill_logo": self.skill_logo,
                        "title": track.title,
                        "skill_id": self.skill_id
                        #"author": t.artist.name,
                        #"album": album.title if match.album else ""
                    }

        if isinstance(match, BandcampAlbum):
            # TODO common play support to return full playlists instead of
            #  individual tracks
            album_score = fuzzy_match(match.title, phrase) * 100
            artist_score = fuzzy_match(match.artist.name, phrase) * 80
            album_score = max(album_score, artist_score)

            # featured track -> very high confidence
            if match.featured_track:
                urls.append(match.featured_track.url)

                score = base_score + album_score

                yield {
                    "match_confidence": min(100, score),
                    "media_type": CommonPlayMediaType.MUSIC,
                    "uri": match.featured_track.stream,
                    "playback": CommonPlayPlaybackType.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": match.featured_track.title,
                    "skill_id": self.skill_id
                    # "author": match.artist.name,
                    # "album": match.title
                }

            # all albums tracks -> high confidence
            for idx, track in enumerate(match.tracks):
                if track.url in urls:
                    continue
                score = base_score + album_score - idx
                yield {
                    "match_confidence": min(100, score),
                    "media_type": CommonPlayMediaType.MUSIC,
                    "uri": track.stream,
                    "playback": CommonPlayPlaybackType.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": track.title,
                    "skill_id": self.skill_id
                    # "author": match.artist.name,
                    # "album": match.title
                }

        if isinstance(match, BandcampTrack):
            track_score = fuzzy_match(match.title, phrase) * 80
            artist_score = fuzzy_match(match.artist.name, phrase) * 100
            track_score = max(track_score, artist_score)
            score = base_score + track_score

            if match.url not in urls:
                yield {
                    "match_confidence": min(100, score),
                    "media_type": CommonPlayMediaType.MUSIC,
                    "uri": match.stream,
                    "playback": CommonPlayPlaybackType.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": match.title,
                    "skill_id": self.skill_id
                    # "author": match.artist.name,
                    # "album": match.album.title if match.album else {}
                }


def create_skill():
    return BandCampSkill()
