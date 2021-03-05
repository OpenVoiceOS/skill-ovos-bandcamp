from py_bandcamp import BandCamper, BandcampAlbum, BandcampTrack, BandcampArtist
from auto_regex import AutoRegex
from ovos_utils.skills.templates.common_play import BetterCommonPlaySkill
from ovos_utils.playback import CPSMatchType, CPSPlayback, CPSMatchConfidence
from os.path import join, dirname
from mycroft.util.parse import fuzzy_match
from ovos_utils.log import LOG
from mycroft.skills.core import intent_file_handler


class BandCampSkill(BetterCommonPlaySkill):
    def __init__(self):
        super(BandCampSkill, self).__init__()
        self.regexes = {}
        self.supported_media = [CPSMatchType.GENERIC, CPSMatchType.MUSIC]
        self._search_cache = {}
        self.default_bg = join(dirname(__file__), "ui", "icon.png")
        self.default_image = join(dirname(__file__), "ui", "icon.png")
        self.skill_logo = join(dirname(__file__), "ui", "icon.png")
        self.skill_icon = join(dirname(__file__), "ui", "icon.png")

    def initialize(self):
        self._load_rx("track_album")
        self._load_rx("track_artist")
        self._load_rx("track_album_artist")
        self._load_rx("n_album")  # track number N from {album}

    @intent_file_handler("bandcamp.intent")
    def handle_search_bandcamp_intent(self, message):
        """ handles bandcamp searches that dont start with "play" which
        means they would miss the CommonPlay framework invocation """
        title = message.data.get("music")
        self.speak_dialog("searching.bandcamp", {"music": title})
        results = self.search(title)
        if len(results):
            self.bus.emit(message.forward("better_cps.play",
                                          {"tracks": results,
                                           "skill_id": self.skill_id}))
        else:
            self.speak_dialog("play.error")

    # parsing
    def _load_rx(self, regex):
        if regex not in self.regexes:
            path = self.find_resource(regex + '.autoregex', "vocab")
            if path:
                with open(path) as f:
                    rules = f.read().split("\n")
                self.regexes[regex] = [r for r in rules if r.strip()]
        return self.regexes[regex]

    def parse_search(self, original):
        """
        parse query type, this logic is more or less provider agnostic
        """
        search_type = "generic"
        if self.voc_match(original, "artist"):
            search_type = "artist"
        elif self.voc_match(original, "track"):
            search_type = "track"
        elif self.voc_match(original, "album"):
            search_type = "album"
        elif self.voc_match(original, "tag"):
            # validate tag
            tag = original.replace(" ", "-").lower().strip()
            if tag in BandCamper.tags():
                search_type = "tag"
        elif self.voc_match(original, "tag_names"):
            # validate tag
            tag = original.replace(" ", "-").lower().strip()
            if tag in BandCamper.tags():
                search_type = "tag"

        # autoregex rules
        data = {}
        for r in self.regexes:
            rx = AutoRegex()
            rx.add_rules(self.regexes[r])
            matches = list(rx.extract(original))
            if len(matches):
                search_type = r
                if search_type == "n_album":
                    pass  # TODO extract number
                data = {"query": matches[0]["track"]}
                data.update(matches[0])

        return search_type, data

    # common play
    def CPS_search(self, phrase, media_type):
        """Analyze phrase to see if it is a play-able phrase with this skill.

        Arguments:
            phrase (str): User phrase uttered after "Play", e.g. "some music"
            media_type (CPSMatchType): requested CPSMatchType to search for

        Returns:
            search_results (list): list of dictionaries with result entries
            {
                "match_confidence": CPSMatchConfidence.HIGH,
                "media_type":  CPSMatchType.MUSIC,
                "uri": "https://audioservice.or.gui.will.play.this",
                "playback": CPSPlayback.GUI,
                "image": "http://optional.audioservice.jpg",
                "bg_image": "http://optional.audioservice.background.jpg"
            }
        """
        base_score = 0
        if media_type == CPSMatchType.MUSIC:
            base_score += 15
            self.extend_timeout(1)

        if self._search_cache.get(phrase):
            LOG.debug("bandcamp search cache hit! " + phrase)
            return self._search_cache[phrase]

        self.extend_timeout(1)
        results = self.search(phrase, base_score)

        if self.voc_match(phrase, "bandcamp"):
            # bandcamp explicitly requested, give max score, but keep
            # confidence order
            for idx, r in enumerate(results):
                results[idx]["match_confidence"] = 100 - idx

        return results

    def search(self, phrase, base_score=0):
        phrase = self.remove_voc(phrase, "bandcamp")

        search_type, query_data = self.parse_search(phrase)
        LOG.debug("Bandcamp search type: " + search_type)

        results = []
        if search_type == "generic":
            for match in BandCamper.search(phrase):
                results += self.bandcamp2cps(match, base_score, phrase)
                break  # for speed

        elif "track" in search_type:
            for match in BandCamper.search_tracks(phrase):
                results += self.bandcamp2cps(match, base_score, phrase)
                break  # for speed

        elif "album" in search_type:
            if query_data.get("album"):
                # album name extracted with regex
                query = query_data["album"]
            else:
                query = phrase

            for match in BandCamper.search_albums(query):
                results += self.bandcamp2cps(match, base_score, phrase)
                break  # for speed

        elif "artist" in search_type:
            for match in BandCamper.search_artists(phrase):
                results += self.bandcamp2cps(match, base_score, phrase)
                break  # for speed

        results = sorted(results, key=lambda k: k["match_confidence"],
                         reverse=True)
        self._search_cache[phrase] = results
        return results

    def bandcamp2cps(self, match, base_score, phrase):
        from pprint import pprint
        print(match.__class__.__name__, match.data)
        print(match.image)

        results = []
        urls = []

        if isinstance(match, BandcampArtist):
            # featured track from featured album -> best score
            if match.featured_track:
                urls.append(match.featured_track.url)
                artist_score = fuzzy_match(match.name, phrase) * 80

                score = base_score + 10 + artist_score

                results.append({
                "match_confidence": min(100, score),
                "media_type": CPSMatchType.MUSIC,
                "uri": match.featured_track.stream,
                "playback": CPSPlayback.AUDIO,
                "image": match.image,
                "bg_image": match.image,
                "skill_icon": self.skill_icon,
                "skill_logo": self.skill_logo,
                "title": match.featured_track.title,
                "skill_id": self.skill_id
                #"author": match.name,
                #"album": match.album.title if match.album else ""
            })

            # featured album tracks -> second best score
            for idx, t in enumerate(match.featured_album.tracks):
                if t.url in urls:
                    continue

                score = base_score + 5 + artist_score - idx
                urls.append(t.url)

                results.append({
                    "match_confidence": min(100, score),
                    "media_type": CPSMatchType.MUSIC,
                    "uri": t.stream,
                    "playback": CPSPlayback.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": t.title,
                    "skill_id": self.skill_id
                    #"author": t.artist.name,
                    #"album": t.album.title if match.album else ""
                })

            # all albums tracks -> third best score
            """
            for idx, album in enumerate(match.albums):
                for idx2, t in enumerate(album.tracks):
                    if t.url in urls:
                        continue
                    score = base_score + 2 + artist_score - idx - idx2
                    
                    urls.append(t.url)
                    results.append({
                        "match_confidence": min(100, score + 5),
                        "media_type": CPSMatchType.MUSIC,
                        "uri": t.stream,
                        "playback": CPSPlayback.AUDIO,
                        "image": match.image,
                        "bg_image": match.image,
                        "skill_icon": self.skill_icon,
                        "skill_logo": self.skill_logo,
                        "title": t.title,
                        "skill_id": self.skill_id
                        #"author": t.artist.name,
                        #"album": album.title if match.album else ""
                    })
            """

        if isinstance(match, BandcampAlbum):
            # featured track -> best score
            if match.featured_track:
                urls.append(match.featured_track.url)

                album_score = fuzzy_match(match.title, phrase) * 80
                score = base_score + 5 + album_score

                results.append({
                "match_confidence": min(100, score),
                "media_type": CPSMatchType.MUSIC,
                "uri": match.featured_track.stream,
                "playback": CPSPlayback.AUDIO,
                "image": match.image,
                "bg_image": match.image,
                "skill_icon": self.skill_icon,
                "skill_logo": self.skill_logo,
                "title": match.featured_track.title,
                "skill_id": self.skill_id
               # "author": match.artist.name,
               # "album": match.title
            })

            # all albums tracks -> secondbest score
            for idx, t in enumerate(match.tracks):
                if t.url in urls:
                    continue
                score = base_score + album_score - idx
                results.append({
                    "match_confidence": min(100, score),
                    "media_type": CPSMatchType.MUSIC,
                    "uri": t.stream,
                    "playback": CPSPlayback.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": t.title,
                    "skill_id": self.skill_id
                    #"author": match.artist.name,
                    #"album": match.title
                })

        if isinstance(match, BandcampTrack):
            track_score = fuzzy_match(match.title, phrase) * 80
            score = base_score + track_score + 5
            if match.url not in urls:
                results.append({
                    "match_confidence": min(100, score),
                    "media_type": CPSMatchType.MUSIC,
                    "uri": match.stream,
                    "playback": CPSPlayback.AUDIO,
                    "image": match.image,
                    "bg_image": match.image,
                    "skill_icon": self.skill_icon,
                    "skill_logo": self.skill_logo,
                    "title": match.title,
                    "skill_id": self.skill_id
                    #"author": match.artist.name,
                    #"album": match.album.title if match.album else {}
                })

        return results


def create_skill():
    return BandCampSkill()
