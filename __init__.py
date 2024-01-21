from os.path import join, dirname

from json_database import JsonStorageXDG
from ovos_bus_client.message import Message
from ovos_utils import classproperty, timed_lru_cache
from ovos_utils.log import LOG
from ovos_utils.ocp import MediaType, PlaybackType
from ovos_utils.parse import fuzzy_match
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators.ocp import ocp_search, ocp_featured_media
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
from py_bandcamp import BandCamp


class BandCampSkill(OVOSCommonPlaybackSkill):
    def __init__(self, *args, **kwargs):
        self.supported_media = [MediaType.MUSIC]
        self.skill_icon = join(dirname(__file__), "ui", "logo.png")
        self.archive = JsonStorageXDG("BandCamp", subfolder="OCP")
        self.albums = JsonStorageXDG("BandCampPlaylists", subfolder="OCP")
        super().__init__(*args, **kwargs)

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=True,
                                   requires_internet=True)

    def initialize(self):
        self.precache()
        self.add_event(f"{self.skill_id}.precache", self.precache)
        self.bus.emit(Message(f"{self.skill_id}.precache"))

    def precache(self, message: Message = None):
        """cache searches and register some helper OCP keywords
        populates featured_media
        """
        def norm(u):
            return u.split('(')[0].replace("-", " ").strip()

        artist_names = [v["artist"] for v in self.archive.values()]
        song_names = [norm(v["title"]) for v in self.archive.values()]
        album_names = [norm(v["album"]) for v in self.albums.values()]

        if message is not None:
            for query in self.settings.get("featured_tracks", []):
                for t in self.search_bandcamp(query, searchtype="tracks"):
                    artist_names.append(t["artist"])
                    song_names.append(t["title"])
                    song_names.append(norm(t["title"]))
            for query in self.settings.get("featured_artists", []):
                for r in self.search_bandcamp(query, searchtype="artists"):
                    pl = r["playlist"]
                    for t in pl:
                        artist_names.append(t["artist"])
                        song_names.append(t["title"])
                        song_names.append(norm(t["title"]))
                        album_names.append(t["album"])
                        album_names.append(norm(t["album"]))
            # by default ensure something for featured_media decorator
            for query in self.settings.get("featured_albums", ["Compressorhead party machine"]):
                for r in self.search_bandcamp(query, searchtype="sets"):
                    pl = r["playlist"]
                    for t in pl:
                        artist_names.append(t["artist"])
                        song_names.append(t["title"])
                        song_names.append(norm(t["title"]))
                        album_names.append(t["album"])
                        album_names.append(norm(t["album"]))

        artist_names = list(set([a.replace("-", " ") for a in artist_names if a.strip()]))
        song_names = list(set([a.replace("-", " ") for a in song_names if a.strip()]))
        album_names = list(set([a.replace("-", " ") for a in album_names if a.strip()]))
        if len(artist_names):
            self.register_ocp_keyword(MediaType.MUSIC, "artist_name", artist_names)
        if len(song_names):
            self.register_ocp_keyword(MediaType.MUSIC, "song_name", song_names)
        if len(album_names):
            self.register_ocp_keyword(MediaType.MUSIC, "album_name", album_names)
        self.register_ocp_keyword(MediaType.MUSIC, "music_streaming_provider", ["Bandcamp", "band camp"])
        self.register_ocp_keyword(MediaType.MUSIC, "music_genre", ["indie", "rock", "metal", "pop", "jazz"])
        # self.export_ocp_keywords_csv("bandcamp.csv")

    @timed_lru_cache(seconds=3600 * 3)
    def search_bandcamp(self, phrase, searchtype="artists"):
        phrase = self.remove_voc(phrase, "bandcamp")

        if searchtype == "tracks":
            for match in BandCamp.search_tracks(phrase):
                artist_name = match.artist.name
                score = fuzzy_match(match.title, phrase) * 100
                t = {
                    "match_confidence": min(100, score),
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + match.url,
                    "playback": PlaybackType.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "duration": match.duration * 1000,
                    "skill_icon": self.skill_icon,
                    "title": match.title + f" ({artist_name})",
                    "artist": artist_name,
                    "skill_id": self.skill_id
                }
                self.archive[t["uri"]] = t
                yield t
        elif searchtype == "artists":
            for match in BandCamp.search_artists(phrase):
                artist_name = match.name
                score = fuzzy_match(artist_name, phrase) * 100
                # all albums
                for idx, album in enumerate(match.albums):
                    pl = [{
                        "match_confidence": min(100, score) - idx2,
                        "media_type": MediaType.MUSIC,
                        "uri": "bandcamp//" + track.url,
                        "playback": PlaybackType.AUDIO,
                        "image": track.image or album.image or match.image,
                        "bg_image": album.image or match.image,
                        "skill_icon": self.skill_icon,
                        "duration": track.duration * 1000,
                        "title": track.title,
                        "artist": artist_name,
                        "skill_id": self.skill_id,
                        "album": album.title
                    } for idx2, track in enumerate(album.tracks)]

                    if pl:
                        for t in pl:
                            self.archive[t["uri"]] = t
                        entry = {
                            "match_confidence": score - idx,
                            "media_type": MediaType.AUDIO,
                            "playback": PlaybackType.AUDIO,
                            "playlist": pl,  # return full playlist result
                            "image": album.image or match.image,
                            "bg_image": album.image or match.image,
                            "skill_icon": self.skill_icon,
                            "album": album.title,
                            "duration": sum(t["duration"] for t in pl),
                            "title": album.title + f" ({artist_name}|Full Album)",
                            "skill_id": self.skill_id
                        }
                        self.albums[album.title] = entry
                        yield entry
        elif searchtype == "sets":
            for album in BandCamp.search_albums(phrase):
                artist_name = album.artist.name
                album_score = fuzzy_match(album.title, phrase) * 100
                artist_score = fuzzy_match(artist_name, phrase) * 100
                score = artist_score * 0.3 + album_score * 0.7

                pl = [{
                    "match_confidence": min(100, score) - idx,
                    "media_type": MediaType.MUSIC,
                    "uri": "bandcamp//" + track.url,
                    "playback": PlaybackType.AUDIO,
                    "image": track.image or album.image,
                    "bg_image": album.image,
                    "skill_icon": self.skill_icon,
                    "title": track.title,
                    "artist": artist_name,
                    "duration": track.duration * 1000,
                    "skill_id": self.skill_id,
                    "album": album.title
                } for idx, track in enumerate(album.tracks)]

                if pl:
                    for t in pl:
                        self.archive[t["uri"]] = t
                    entry = {
                        "match_confidence": score,
                        "media_type": MediaType.AUDIO,
                        "playback": PlaybackType.AUDIO,
                        "playlist": pl,  # return full playlist result
                        "image": album.image,
                        "bg_image": album.image,
                        "skill_icon": self.skill_icon,
                        "album": album.title,
                        "artist": artist_name,
                        "duration": sum(t["duration"] for t in pl),
                        "title": album.title + f" (Full Album)",
                        "skill_id": self.skill_id
                    }
                    self.albums[album.title] = entry
                    yield entry

        self.archive.store()
        self.albums.store()

    @ocp_featured_media()
    def featured_media(self):
        return [{
            "title": video["title"],
            "image": video["thumbnail"],
            "match_confidence": 80,
            "media_type": MediaType.MUSIC,
            "uri": uri,
            "playback": PlaybackType.AUDIO,
            "skill_icon": self.skill_icon,
            "bg_image": video["thumbnail"],
            "skill_id": self.skill_id
        } for uri, video in self.archive.items()]

    def get_playlist(self, score=50, num_entries=50):
        pl = self.featured_media()[:num_entries]
        return {
            "match_confidence": score,
            "media_type": MediaType.MUSIC,
            "playlist": pl,
            "playback": PlaybackType.AUDIO,
            "skill_icon": self.skill_icon,
            "image": self.skill_icon,
            "title": "Bandcamp Featured Media (Playlist)",
            "author": "Bandcamp"
        }

    # common play
    @ocp_search()
    def search_db(self, phrase, media_type=MediaType.GENERIC):
        base_score = 30 if media_type == MediaType.MUSIC else 0
        entities = self.ocp_voc_match(phrase)

        base_score += 30 * len(entities)

        artist = entities.get("artist_name")
        song = entities.get("song_name")
        playlist = entities.get("album_name")
        skill = "music_streaming_provider" in entities  # skill matched

        if playlist:
            LOG.debug("searching Bandcamp albums cache")
            for k, pl in self.albums.items():
                if playlist.lower() in k.lower():
                    pl["match_confidence"] = base_score + 35
                    yield pl

        urls = []
        if song:
            LOG.debug("searching Bandcamp songs cache")
            for video in self.archive.values():
                if song.lower() in video["title"].lower():
                    s = base_score + 45
                    if artist and (artist.lower() in video["title"].lower() or
                                   artist.lower() in video.get("artist", "").lower()):
                        s += 30
                    video["match_confidence"] = min(100, s)
                    yield video
                    urls.append(video["uri"])
        if artist:
            LOG.debug("searching Bandcamp artist cache")
            for video in self.archive.values():
                if video["uri"] in urls:
                    continue
                if artist.lower() in video["title"].lower() or \
                        artist.lower() in video.get("artist", "").lower():
                    video["match_confidence"] = min(100, base_score + 35)
                    yield video
                    urls.append(video["uri"])

        if skill:
            yield self.get_playlist()

    @ocp_search()
    def search_bandcamp_artist(self, phrase, media_type=MediaType.GENERIC):
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 30
        if media_type == MediaType.MUSIC:
            base_score += 15
        phrase = self.remove_voc(phrase, "bandcamp")
        for res in self.search_bandcamp(phrase):
            res["match_confidence"] += base_score
            yield res


if __name__ == "__main__":
    from ovos_utils.messagebus import FakeBus

    s = BandCampSkill(bus=FakeBus(), skill_id="skill-ovos-bandcamp.openvoiceos")

    # usually happens in init
    # s.settings["featured_tracks"] = ["astronaut problems"]
    # s.settings["featured_artists"] = ["planet of the dead", "compressorhead"]
    # s.settings["featured_albums"] = ["Fear of a Dead Planet"]
    # s.precache(Message(""))
    #######
    for r in s.search_db("astronaut problems"):
        print(r)
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://deadunicorn.bandcamp.com/track/astronaut-problems', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3545261915_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3545261915_10.jpg', 'duration': 0, 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Astronaut Problems (Dead Unicorn)', 'artist': 'Dead Unicorn', 'skill_id': 'skill-ovos-bandcamp.openvoiceos'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://deadunicorn.bandcamp.com/track/astronaut-problems-live', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3840993898_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3840993898_10.jpg', 'duration': 0, 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Astronaut Problems (live) (Dead Unicorn)', 'artist': 'Dead Unicorn', 'skill_id': 'skill-ovos-bandcamp.openvoiceos'}

    for r in s.search_db("compressorhead"):
        print(r)
        # {'match_confidence': 100, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/compressorhead', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Compressorhead', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/these-bots-are-made-for-rocking', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'These Bots Are Made for Rocking', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/speed-walking-lady', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Speed Walking Lady', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/zombies-vs-robots', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Zombies vs. Robots', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/these-people-like-to-dance', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'These People Like to Dance', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/the-contender', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'The Contender', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/gen-generic', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Gen Generic', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/i-am-what-i-am', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'I Am What I Am', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/fleisch', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Fleisch', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/the-place-im-at', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': "The Place I'm At", 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/let-there-be-light', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Let There Be Light', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/loose-screw', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Loose Screw', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/my-girlfriends-a-robot', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': "My Girlfriend's a Robot", 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/party-machine', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Party Machine', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}
        # {'match_confidence': 90, 'media_type': 2, 'uri': 'bandcamp//https://compressorhead.bandcamp.com/track/made-to-be', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3316961394_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Made To Be', 'artist': 'Compressorhead', 'duration': 0, 'skill_id': 't.fake', 'album': 'party-machine'}

    for r in s.search_db("nostromo"):
        print(r)
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/nostromo', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'Nostromo', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}

    for r in s.search_db("planet of the dead"):
        print(r)
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/gom-jabbar', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'Gom Jabbar', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/pilgrim', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'Pilgrim', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/nostromo', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'Nostromo', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/the-sprawl', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'The Sprawl', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/escape-from-smiths-grove', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': "Escape from Smith's Grove", 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/directive-iv', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'Directive IV', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/the-cursed-earth', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'The Cursed Earth', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/the-great-wave', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'bg_image': 'https://f4.bcbits.com/img/a0090508043_10.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'duration': 0, 'title': 'The Great Wave', 'artist': 'Planet of the Dead', 'skill_id': 't.fake', 'album': 'Pilgrims'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/the-eternal-void', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'The Eternal Void', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/mind-killer', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Mind Killer', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/a-million-deaths', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'A Million Deaths', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/nashwan', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Nashwan', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/entropy', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Entropy', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/walk-the-earth', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Walk the Earth', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/iguanodon', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Iguanodon', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
        # {'match_confidence': 60, 'media_type': 2, 'uri': 'bandcamp//https://planetofthedead.bandcamp.com/track/snake-wizard', 'playback': 2, 'image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'bg_image': 'https://f4.bcbits.com/img/a3408335541_7.jpg', 'skill_icon': 'https://github.com/OpenVoiceOS/ovos-ocp-audio-plugin/raw/master/ovos_plugin_common_play/ocp/res/ui/images/ocp.png', 'title': 'Snake Wizard', 'artist': 'Planet of the Dead', 'duration': 0, 'skill_id': 't.fake', 'album': 'fear-of-a-dead-planet'}
