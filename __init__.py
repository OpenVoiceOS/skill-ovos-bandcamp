from os.path import join, dirname

from mycroft.util.parse import fuzzy_match
from ovos_plugin_common_play.ocp import MediaType, \
    PlaybackType
from ovos_utils.parse import fuzzy_match
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill, \
    ocp_search
from py_bandcamp import BandCamper


class BandCampSkill(OVOSCommonPlaybackSkill):
    def __init__(self):
        super(BandCampSkill, self).__init__()
        self.supported_media = [MediaType.GENERIC, MediaType.MUSIC]
        self.skill_icon = join(dirname(__file__), "ui", "icon.png")

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
            # artist top tracks
            for match in BandCamper.search_artists(phrase):
                artist_name = match.name
                artist_score = fuzzy_match(artist_name, phrase) * 100
                score = base_score + artist_score

                # all albums
                for idx, album in enumerate(match.albums):
                    pl = [{
                        "match_confidence": min(100, score) - idx2,
                        "media_type": MediaType.MUSIC,
                        "uri": "bandcamp//" + track.watch_url,
                        "playback": PlaybackType.AUDIO,
                        "image": track.thumbnail_url or album.thumbnail_url or match.thumbnail_url,
                        "bg_image": album.thumbnail_url or match.thumbnail_url,
                        "skill_icon": self.skill_icon,
                        "title": track.title,
                        "artist": artist_name,
                        "skill_id": self.skill_id,
                        "album": album.title
                    } for idx2, track in enumerate(album.tracks)]

                    if pl:
                        yield {
                            "match_confidence": score - idx,
                            "media_type": MediaType.AUDIO,
                            "playback": PlaybackType.AUDIO,
                            "playlist": pl,  # return full playlist result
                            "image": album.thumbnail_url or match.thumbnail_url,
                            "bg_image": album.thumbnail_url or match.thumbnail_url,
                            "skill_icon": self.skill_icon,
                            "album": album.title,
                            "title": album.title + f" ({artist_name}|Full Album)",
                            "skill_id": self.skill_id
                        }
        except Exception as e:
            pass

    #@ocp_search()
    def search_bandcamp_tracks(self, phrase,
                               media_type=MediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 15
        if media_type == MediaType.MUSIC:
            base_score += 5
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            for match in BandCamper.search_tracks(phrase):
                artist_name = match.artist.name
                track_score = fuzzy_match(match.title, phrase) * 100
                score = base_score + track_score
                yield {
                    "match_confidence": min(100, score),
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + match.watch_url,
                    "playback": PlaybackType.AUDIO,
                    "image": match.thumbnail_url,
                    "bg_image": match.thumbnail_url,
                    "skill_icon": self.skill_icon,
                    "title": match.title + f" ({artist_name})",
                    "artist": artist_name,
                    "skill_id": self.skill_id
                }
        except:
            pass

    #@ocp_search() # deactivated due to many bad matches, users rarely ask
    # for album name anyways... maybe add dedicated intent for albums??
    def search_bandcamp_album(self, phrase,
                              media_type=MediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 10
        if media_type == MediaType.MUSIC:
            base_score += 10
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            for album in BandCamper.search_albums(phrase):
                artist_name = album.artist.name
                album_score = fuzzy_match(album.title, phrase) * 100
                artist_score = fuzzy_match(artist_name, phrase) * 100
                score = artist_score * 0.3 + album_score * 0.7

                pl = [{
                    "match_confidence": min(100, score) - idx,
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + track.watch_url,
                    "playback": PlaybackType.AUDIO,
                    "image": track.thumbnail_url or album.thumbnail_url,
                    "bg_image": album.thumbnail_url,
                    "skill_icon": self.skill_icon,
                    "title": track.title,
                    "skill_id": self.skill_id,
                    "album": album.title
                } for idx, track in enumerate(album.tracks)]

                if pl:
                    yield {
                        "match_confidence": score,
                        "media_type": MediaType.AUDIO,
                        "playback": PlaybackType.AUDIO,
                        "playlist": pl,  # return full playlist result
                        "image": album.thumbnail_url,
                        "bg_image": album.thumbnail_url,
                        "skill_icon": self.skill_icon,
                        "album": album.title,
                        "title": album.title + f" (Full Album)",
                        "skill_id": self.skill_id
                    }
        except:
            pass


def create_skill():
    return BandCampSkill()
