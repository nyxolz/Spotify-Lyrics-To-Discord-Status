import requests
import re
import time
import pylast
from typing import Optional, Dict, List, Tuple

class SpotifyLyricsManager:
    def __init__(self, sp_dc: str = None, early_delay_ms: int = 700,
                 lastfm_api_key: str = None, lastfm_api_secret: str = None,
                 lastfm_username: str = None, lastfm_password_hash: str = None):
        self.early_delay_ms = early_delay_ms
        self.current_track_id = None
        self.current_lyrics: List[Tuple[int, str]] = []
        self.last_lyric = None
        self.lyrics_index = 0
        self._track_start_real = None
        self._track_duration_ms = None

        self.network = pylast.LastFMNetwork(
            api_key=lastfm_api_key,
            api_secret=lastfm_api_secret,
            username=lastfm_username,
            password_hash=pylast.md5(lastfm_password_hash)
        )

    def get_current_track(self) -> Optional[Dict]:
        try:
            user = self.network.get_user(self.network.username)
            np = user.get_now_playing()
            if not np:
                return None
            track_name = np.get_name()
            artist = np.get_artist().get_name()
            track_id = f"{artist}_{track_name}".lower().replace(" ", "_")
            try:
                duration_ms = int(np.get_duration()) * 1000
            except Exception:
                duration_ms = 240000
            if track_id != self.current_track_id:
                self._track_start_real = time.time()
                self._track_duration_ms = duration_ms
            progress_ms = int((time.time() - (self._track_start_real or time.time())) * 1000)
            progress_ms = max(0, min(progress_ms, duration_ms))
            return {
                "track_id": track_id,
                "track_name": track_name,
                "artist": artist,
                "duration_ms": duration_ms,
                "progress_ms": progress_ms,
                "is_playing": True
            }
        except Exception:
            return None

    def _fetch_lyrics(self, track_name: str, artist: str) -> List[Tuple[int, str]]:
        try:
            resp = requests.get(
                "https://lrclib.net/api/search",
                params={"track_name": track_name, "artist_name": artist},
                timeout=10
            )
            if resp.status_code != 200:
                return []
            results = resp.json()
            if not results:
                return []
            synced = next((r for r in results if r.get("syncedLyrics")), None)
            if not synced:
                return []
            lines = []
            for line in synced["syncedLyrics"].splitlines():
                match = re.match(r'\[(\d+):(\d+\.\d+)\](.*)', line)
                if match:
                    ms = int((int(match.group(1)) * 60 + float(match.group(2))) * 1000)
                    text = match.group(3).strip()
                    lines.append((ms, text))
            return sorted(lines, key=lambda x: x[0])
        except Exception:
            return []

    def get_current_lyric(self, track_info: Dict) -> Optional[str]:
        track_id = track_info["track_id"]
        progress_ms = track_info["progress_ms"]
        if track_id != self.current_track_id:
            self.current_track_id = track_id
            self.current_lyrics = self._fetch_lyrics(track_info["track_name"], track_info["artist"])
            self.last_lyric = None
            self.lyrics_index = 0
        if not self.current_lyrics:
            return None
        adjusted_ms = progress_ms + self.early_delay_ms
        current_lyric = None
        for i, (ts, text) in enumerate(self.current_lyrics):
            if adjusted_ms >= ts:
                current_lyric = text
                self.lyrics_index = i
            else:
                break
        if not current_lyric or current_lyric == self.last_lyric:
            return None
        self.last_lyric = current_lyric
        return current_lyric

    def clean_metadata(self, text: str) -> str:
        text = re.sub(r'\s*-\s*.*Remaster.*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\[.*\]', '', text)
        text = re.sub(r'\s*\(feat\..*?\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(with.*?\)', '', text, flags=re.IGNORECASE)
        return text.strip()

    def get_fallback_track_info(self, track_info: Dict) -> str:
        return f"♪ {track_info['artist']} - {self.clean_metadata(track_info['track_name'])}"
