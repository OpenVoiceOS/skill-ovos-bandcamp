from os.path import join, dirname
from typing import Iterable

from ovos_utils import classproperty
from ovos_workshop.backwards_compat import MediaType, PlaybackType, Playlist, PluginStream
from ovos_utils.parse import fuzzy_match
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import ocp_search
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
from py_bandcamp import BandCamp


class BandCampSkill(OVOSCommonPlaybackSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(skill_icon=join(dirname(__file__), "res", "logo.png"),
                         supported_media=[MediaType.GENERIC, MediaType.MUSIC],
                         *args, **kwargs)

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=True,
                                   network_before_load=True,
                                   gui_before_load=False,
                                   requires_internet=True,
                                   requires_network=True,
                                   requires_gui=False,
                                   no_internet_fallback=False,
                                   no_network_fallback=False,
                                   no_gui_fallback=True)

    # common play
    @ocp_search()
    def search_bandcamp_artist(self, phrase, media_type=MediaType.GENERIC) -> Iterable[Playlist]:
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 30
        if media_type == MediaType.MUSIC:
            base_score += 15
        phrase = self.remove_voc(phrase, "bandcamp")
        try:
            # artist top tracks
            for match in BandCamp.search_artists(phrase):
                artist_name = match.name
                artist_score = fuzzy_match(artist_name, phrase) * 100
                score = base_score + artist_score

                # all albums
                for idx, album in enumerate(match.albums):
                    pl = Playlist(match_confidence=score - idx,
                                  media_type=MediaType.MUSIC,
                                  playback=PlaybackType.AUDIO,
                                  image=album.image or match.image,
                                  skill_icon=self.skill_icon,
                                  skill_id=self.skill_id,
                                  title=album.title + f" ({artist_name}|Full Album)",
                                  artist=artist_name
                                  )
                    for idx2, track in enumerate(album.tracks):
                        pl.append(PluginStream(
                            match_confidence=min(100, score) - idx2,
                            extractor_id="bandcamp",
                            stream=track.url,
                            title=track.title,
                            image=track.image or album.image or match.image,
                            artist=artist_name,
                            length=track.duration * 1000,
                            skill_id=self.skill_id,
                            skill_icon=self.skill_icon,
                            media_type=MediaType.MUSIC,
                            playback=PlaybackType.AUDIO
                        ))
                    if pl:
                        yield pl
        except Exception as e:
            pass

    # @ocp_search()
    def search_bandcamp_tracks(self, phrase, media_type=MediaType.GENERIC) -> Iterable[PluginStream]:
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 15
        if media_type == MediaType.MUSIC:
            base_score += 5
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            for match in BandCamp.search_tracks(phrase):
                artist_name = match.artist.name
                track_score = fuzzy_match(match.title, phrase) * 100
                score = base_score + track_score
                yield PluginStream(
                    match_confidence=min(100, score),
                    extractor_id="bandcamp",
                    stream=match.url,
                    title=match.title + f" ({artist_name})",
                    image=match.image,
                    artist=artist_name,
                    length=match.duration * 1000,
                    skill_id=self.skill_id,
                    skill_icon=self.skill_icon,
                    media_type=MediaType.MUSIC,
                    playback=PlaybackType.AUDIO
                )
        except:
            pass

    # @ocp_search() # deactivated due to many bad matches, users rarely ask
    # for album name anyways... maybe add dedicated intent for albums??
    def search_bandcamp_album(self, phrase, media_type=MediaType.GENERIC) -> Iterable[Playlist]:
        base_score = 0
        if self.voc_match(phrase, "bandcamp"):
            base_score = 10
        if media_type == MediaType.MUSIC:
            base_score += 10
        phrase = self.remove_voc(phrase, "bandcamp")

        try:
            for album in BandCamp.search_albums(phrase):
                artist_name = album.artist.name
                album_score = fuzzy_match(album.title, phrase) * 100
                artist_score = fuzzy_match(artist_name, phrase) * 100
                score = artist_score * 0.3 + album_score * 0.7

                pl = Playlist(
                    title=album.title + f" (Full Album)",
                    artist=artist_name,
                    image=album.image,
                    match_confidence=score,
                    skill_id=self.skill_id,
                    skill_icon=self.skill_icon,
                    media_type=MediaType.MUSIC,
                    playback=PlaybackType.AUDIO
                )
                for idx, track in enumerate(album.tracks):
                    pl.append(PluginStream(
                        match_confidence=min(100, score) - idx,
                        extractor_id="bandcamp",
                        stream=track.url,
                        title=track.title,
                        image=track.image or album.image,
                        artist=artist_name,
                        length=track.duration * 1000,
                        skill_id=self.skill_id,
                        skill_icon=self.skill_icon,
                        media_type=MediaType.MUSIC,
                        playback=PlaybackType.AUDIO
                    ))
                if pl:
                    yield pl
        except:
            pass



if __name__ == "__main__":
    from ovos_utils.messagebus import FakeBus
    from ovos_utils.log import LOG

    LOG.set_level("DEBUG")

    s = BandCampSkill(bus=FakeBus(), skill_id="t.fake")
    for r in s.search_bandcamp_artist("planet of the dead", MediaType.MUSIC):
        print(r)
        # Playlist(title='Pilgrims (Planet of the Dead|Full Album)', artist='Planet of the Dead', position=0, image='https://f4.bcbits.com/img/a0090508043_10.jpg', match_confidence=103.88888888888889, skill_id='t.fake', skill_icon='/home/miro/PycharmProjects/OCPSkills/skill-ovos-bandcamp/res/logo.png', playback=<PlaybackType.AUDIO: 2>, media_type=<MediaType.MUSIC: 2>)
        # Playlist(title='Fear of a Dead Planet (Planet of the Dead|Full Album)', artist='Planet of the Dead', position=0, image='https://f4.bcbits.com/img/a3408335541_10.jpg', match_confidence=102.88888888888889, skill_id='t.fake', skill_icon='/home/miro/PycharmProjects/OCPSkills/skill-ovos-bandcamp/res/logo.png', playback=<PlaybackType.AUDIO: 2>, media_type=<MediaType.MUSIC: 2>)
