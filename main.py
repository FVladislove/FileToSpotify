import dataclasses
import logging
import os
import json
import eyed3
import spotipy
import copy
from spotipy.oauth2 import SpotifyOAuth
from typing import List, Dict
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field

logger = logging.getLogger("app_logger")
logger.handlers.append(logging.StreamHandler())

logger.setLevel(logging.DEBUG)
eyed3.log.setLevel("ERROR")

spotify: spotipy.Spotify = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=os.environ["SPOTIPY_CLIENT_ID"],
        client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
        redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
        scope="playlist-read-private playlist-modify-private"
    ))


@dataclass
class Song:
    path_to_file: str
    artist: str = None
    title: str = None
    spotify_id: str = None
    problems: list = field(default_factory=list)


class SongJSONEncoder(json.JSONEncoder):
    def default(self, o: Song):
        return dataclasses.asdict(o)


class SongJsonDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    @staticmethod
    def object_hook(dct):
        if 'path_to_file' in dct:
            return Song(dct['path_to_file'],
                        dct['artist'],
                        dct['title'],
                        dct['spotify_id'],
                        dct['problems'])
        return dct


class FuncCallsCounter:
    def __init__(self, func):
        self.func = func
        self.calls_counter = 0

    def __call__(self, *args, **kwargs):
        self.calls_counter += 1
        return self.func(*args, **kwargs)


def merge_dicts_with_list_values(dict1, dict2):
    res = copy.deepcopy(dict1)
    for key, value in dict2.items():
        if key in res:
            res[key] += value
        else:
            res[key] = value
    return res


@FuncCallsCounter
def process_song(path_to_song: str) -> Song:
    logger.debug("Start song processing")
    logger.debug(f"Path:\t{path_to_song}")

    song_file_data = eyed3.load(path_to_song)
    song = Song(path_to_song)
    if song_file_data is None:
        song.problems.append("Failed to process file")
    else:
        if song_file_data.tag is None:
            song.problems.append("Tag is undefined")

        if song_file_data.tag.artist is None:
            song.problems.append("Artist is undefined")
        else:
            song.artist = song_file_data.tag.artist

        if song_file_data.tag.title is None:
            song.problems.append("Title is undefined")
        else:
            song.title = song_file_data.tag.title

    if len(song.problems) != 0:
        return song

    search = spotify.search(q=song.title + " " + song.artist, type="track", limit=1)

    try:
        song.spotify_id = search['tracks']['items'][0]['id']
        logger.debug("Processed song\t\tartist: {0:<20} title: {1:<30} song_id: {2:<20}"
                     .format(song.artist, song.title, song.spotify_id))
    except IndexError:
        song.problems.append("Song not found")
        logger.debug("NOT processed song\tartist: {0:<20} title: {1:<20}"
                     .format(song.artist, song.title))

    return song


def load_songs(path: str) -> [list, list]:
    logger.debug(f"Load songs from {path}")

    songs = defaultdict(list)
    not_found_songs = defaultdict(list)

    for element in os.listdir(path):
        path_to_el = path + '\\' + element
        if os.path.isdir(path_to_el):
            load = load_songs(path_to_el)

            logger.debug(f"Merge dicts")
            songs = merge_dicts_with_list_values(songs, load[0])
            not_found_songs = merge_dicts_with_list_values(not_found_songs, load[1])

        elif path_to_el[len(path_to_el) - 4:] == ".mp3":
            song_info = process_song(path_to_el)
            print("Number of processed song: {0}".format(process_song.calls_counter), end='\r')
            if song_info.spotify_id is not None:
                songs[song_info.artist].append(song_info)
            else:
                not_found_songs[song_info.artist].append(song_info)

    return songs, not_found_songs


def get_playlist_id_by_name(name):
    logger.debug(f"Getting '{name}' playlist id")

    playlists = spotify.current_user_playlists()['items']
    for playlist in playlists:
        if playlist['name'] == name:
            return playlist['id']


def dump_not_founded_songs_to_file(obj, name_of_file: str):
    songs_str = json.dumps(obj, indent=4, cls=SongJSONEncoder, ensure_ascii=False)
    with open(name_of_file, 'w', encoding="UTF-8") as f:
        f.write(songs_str)
    print(f"The file with the songs not found is located in the same path as the script and named {name_of_file}")


def add_songs_to_playlist(playlist_id, songs: Dict[str, List[Song]]):
    logger.debug("Start adding songs to playlist")

    for artist, tracks in songs.items():
        logger.debug(f"Adding {artist} tracks to playlist")

        ids = [track.spotify_id for track in tracks]
        spotify.playlist_add_items(playlist_id, ids)


def main():
    path = input("Input path to folder with songs: ")

    f_songs, nf_songs = load_songs(path)

    if len(nf_songs) != 0:
        dump_not_founded_songs_to_file(nf_songs, 'not_found_songs.json')

    playlist_name = input("Input playlist name: ")
    spotify.user_playlist_create(spotify.current_user()['id'], playlist_name)
    playlist_id = get_playlist_id_by_name(playlist_name)

    add_songs_to_playlist(playlist_id, f_songs)


if __name__ == '__main__':
    main()
