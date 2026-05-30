import json
import time # time-python - idk if pip installing time-python is needed. i think it comes with python but idk
import requests
import re
from better_profanity import profanity
from spotify_lyrics import SpotifyLyricsManager


def split_line_at_last_word(text, current_time_ms, lyrics_data): # this is a bit buggy
    words = text.split()
    if len(words) <= 1:
        return [text]
    
    last_word = words[-1]
    rest_of_line = ' '.join(words[:-1])
    
    current_lyric_start = None
    next_lyric_start = None
    
    for i, (timestamp_ms, lyric_text) in enumerate(lyrics_data):
        if lyric_text == text:
            current_lyric_start = timestamp_ms
            if i + 1 < len(lyrics_data):
                next_lyric_start = lyrics_data[i + 1][0]
            break
    
    if current_lyric_start is not None and next_lyric_start is not None:
        total_duration = next_lyric_start - current_lyric_start
        first_part_duration = max(total_duration - 2000, total_duration * 0.6)
        
        time_into_lyric = current_time_ms - current_lyric_start
        
        if (time_into_lyric >= 0 and 
            time_into_lyric >= first_part_duration and 
            time_into_lyric < total_duration):
            return [rest_of_line, last_word, 'last']
        else:
            return [rest_of_line, last_word, 'first']
    else:
        return [rest_of_line, last_word, 'first']


def filter_cuss_words(text):
    profanity.load_censor_words()
    
    def replace_word(match):
        word = match.group(0)
        return '#' * len(word)
    
    words = list(profanity.CENSOR_WORDSET)
    words.append('thot')  # added word that wasn't in the better profanity libary
    pattern = r'\b(' + '|'.join(re.escape(str(word)) for word in words) + r')\b'
    
    return re.sub(pattern, replace_word, text, flags=re.IGNORECASE)


# thanks to @the_real_universal_cat for this method <3
def change_status(token, message, emoji_name, emoji_id=None):
    header = {'authorization': token}
    payload = {"custom_status": {"text": message}}
    
    if emoji_id:
        payload["custom_status"].update({"emoji_name": emoji_name, "emoji_id": emoji_id})
    else:
        payload["custom_status"]["emoji_name"] = emoji_name
    
    r = requests.patch("https://discord.com/api/v10/users/@me/settings", 
                      headers=header, json=payload, timeout=2)
    return r.status_code == 200


def load_config():
    with open("config.json", "r") as file:
        return json.load(file)


def process_lyric_status(status, filter_enabled, line_split_enabled, 
                       track_info, spotify_manager, lyric_start_time):
    if filter_enabled:
        status = filter_cuss_words(status)
    
    if line_split_enabled:
        early_progress_ms = track_info['progress_ms'] + spotify_manager.early_delay_ms
        split_result = split_line_at_last_word(status, early_progress_ms, 
                                             spotify_manager.current_lyrics)
        
        if lyric_start_time and (time.time() - lyric_start_time) > 4.0:
            words = status.split()
            if len(words) > 1:
                status = words[-1]
        elif len(split_result) >= 3:
            if split_result[2] == 'first':
                status = split_result[0]
            else:
                status = split_result[1]
    
    return status


def update_discord_status(token, status, emoji_name, last_status):
    if status != last_status:
        print(f"{time.strftime('%I:%M %p')} {status}")
        success = change_status(token, status, emoji_name, None)
        if success:
            print(f"success current status: '{status}'") # yay
        else:
            print(f"failed... so pmo.,,..,: '{status}'") # i would kms
        return status
    return last_status


def main():
    config = load_config()
    token = config["token"]
    filter_enabled = config.get("cuss_word_filter", True)
    line_split_enabled = config.get("line_split_mode", False)
    
    spotify_manager = SpotifyLyricsManager(
    early_delay_ms=config.get("lyrics_early_delay_ms", 700),
    lastfm_api_key=config["lastfm_api_key"],
    lastfm_api_secret=config["lastfm_api_secret"],
    lastfm_username=config["lastfm_username"],
    lastfm_password_hash=config["lastfm_password"]
)

    )

    last_status = None
    last_track_id = None
    lyric_start_time = None
    current_lyric_text = None

    while True:
        try:
            track_info = spotify_manager.get_current_track()
            if track_info:
                track_id = track_info['track_id']
                
                if track_id != last_track_id:
                    last_track_id = track_id
                    last_status = None
                    lyric_start_time = None
                    current_lyric_text = None
                
                current_lyric = spotify_manager.get_current_lyric(track_info)
                if current_lyric:
                    if current_lyric != current_lyric_text:
                        current_lyric_text = current_lyric
                        lyric_start_time = time.time()
                    
                    status = process_lyric_status(current_lyric, filter_enabled, 
                                               line_split_enabled, track_info, 
                                               spotify_manager, lyric_start_time)
                    
                    emoji_name = f"{track_info['artist'][:15]}..."
                    last_status = update_discord_status(token, status, emoji_name, last_status)
                    
                elif current_lyric is None and spotify_manager.last_lyric is not None:
                    if line_split_enabled and spotify_manager.current_lyrics:
                        status = process_lyric_status(spotify_manager.last_lyric, 
                                                   filter_enabled, line_split_enabled, 
                                                   track_info, spotify_manager, 
                                                   lyric_start_time)
                        
                        emoji_name = f"{track_info['artist'][:15]}..."
                        last_status = update_discord_status(token, status, emoji_name, last_status)
                    else:
                        time.sleep(0.1)
                        continue
                else:
                    status = spotify_manager.get_fallback_track_info(track_info)
                    if filter_enabled:
                        status = filter_cuss_words(status)
                    
                    if line_split_enabled:
                        split_result = split_line_at_last_word(status, 0, [])
                        if len(split_result) >= 3:
                            status = split_result[0]
                    
                    emoji_name = "♪"
                    last_status = update_discord_status(token, status, emoji_name, last_status)
            else:
                if last_track_id is not None:
                    last_track_id = None
                    last_status = None

                
                status = "Spotify Lyrics To Discord Status By @unknowingly_exists" # don't fw this (mit license so idc)
                # refer to line 198 for the status emoji

                
                if filter_enabled:
                    status = filter_cuss_words(status)
                
                if line_split_enabled:
                    split_result = split_line_at_last_word(status, 0, [])
                    if len(split_result) >= 3:
                        status = split_result[0]

                
                emoji_name = "🎵" # you can change this emoji to whatever emoji you want

                
                last_status = update_discord_status(token, status, emoji_name, last_status)

            time.sleep(0.1)
        except KeyboardInterrupt: # placed here to get rid of the stupid error message
            print("\nStopped")
            break
        except Exception:
            time.sleep(0.1)


if __name__ == "__main__":
    main()
