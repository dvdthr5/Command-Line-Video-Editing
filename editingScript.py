import json
import os
import re
from typing import Dict, Tuple

from moviepy.editor import VideoFileClip

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "videos")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
FRAME_DATA_PATH = os.path.join(BASE_DIR, "frame_data.json")
FRAME_PAD_FRAMES = 13  # Default padding on each side
DEFAULT_EXTRA_PRE = 0.10
DEFAULT_EXTRA_POST = 0.10


def load_frame_data(path: str = FRAME_DATA_PATH) -> Dict[str, Dict[str, int]]:
    """Return dict loaded from JSON. If missing, create it."""
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({}, handle, indent=2)
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError
            return data
        except ValueError:
            print("Warning: frame_data.json is invalid JSON, resetting to empty.")
            save_frame_data({}, path)
            return {}


def save_frame_data(data: Dict[str, Dict[str, int]], path: str = FRAME_DATA_PATH) -> None:
    """Write dict back to JSON (pretty-printed)."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def parse_time(time_str: str) -> int:
    """Backwards-compatible helper returning whole seconds for manual trim."""
    seconds = parse_time_to_seconds(time_str)
    return int(seconds)


def parse_time_to_seconds(time_str: str) -> float:
    """
    Accept 'ss' or 'mm:ss'. Return float seconds.
    """
    if not time_str:
        raise ValueError("Time string cannot be empty.")
    parts = time_str.split(":")
    if len(parts) == 1:
        if not parts[0].replace(".", "", 1).isdigit():
            raise ValueError("Invalid time format. Use seconds or mm:ss.")
        return float(parts[0])
    if len(parts) == 2:
        minutes, seconds = parts
        if not minutes.isdigit() or not seconds.replace(".", "", 1).isdigit():
            raise ValueError("Invalid mm:ss format.")
        return int(minutes) * 60 + float(seconds)
    raise ValueError("Invalid time format. Use seconds or mm:ss.")


def sanitize_label(label: str) -> str:
    cleaned = "".join(ch for ch in label if ch.isalnum())
    return cleaned or "Unknown"


def normalize_key(value: str) -> str:
    """Lowercase the string and strip spaces so lookups are forgiving."""
    return "".join(ch.lower() for ch in value if not ch.isspace())


def match_character_name(name: str, frame_data: Dict[str, Dict[str, int]]) -> str:
    target = normalize_key(name)
    for key in frame_data:
        if normalize_key(key) == target:
            return key
    return name


def match_move_name(character: str, move: str, frame_data: Dict[str, Dict[str, int]]) -> str:
    moves = frame_data.get(character, {})
    target = normalize_key(move)
    for key in moves:
        if normalize_key(key) == target:
            return key
    return move


def ensure_move_frames(
    character: str,
    move: str,
    frame_data: Dict[str, Dict[str, int]],
    path: str = FRAME_DATA_PATH,
) -> int:
    """Ensure the frame count exists for the character and move, prompting if needed."""
    char_key = match_character_name(character, frame_data)
    frame_data.setdefault(char_key, {})
    move_key = match_move_name(char_key, move, frame_data)
    while True:
        frames = frame_data[char_key].get(move_key)
        if frames is not None:
            return frames
        user_input = input(
            f"Frame count for '{char_key}' move '{move_key}' (integer frames at 60fps): "
        ).strip()
        if not user_input:
            print("Frame count is required to continue.")
            continue
        if not user_input.isdigit():
            print("Please enter a positive integer.")
            continue
        frame_data[char_key][move_key] = int(user_input)
        save_frame_data(frame_data, path)
        print(f"Saved {char_key} -> {move_key}: {frame_data[char_key][move_key]} frames.")


def get_clip_range(
    character: str,
    move: str,
    center_ts: float,
    video_duration: float,
    frame_data: Dict[str, Dict[str, int]],
    frame_data_path: str = FRAME_DATA_PATH,
    fps: float = 60.0,
    extra_pre: float = DEFAULT_EXTRA_PRE,
    extra_post: float = DEFAULT_EXTRA_POST,
) -> Tuple[float, float]:
    """
    Compute [start, end] window around the move using frame data, padding, and clamps.
    """
    frames = ensure_move_frames(character, move, frame_data, frame_data_path)
    duration = frames / fps
    pad_sec = FRAME_PAD_FRAMES / fps
    total_pre = (duration / 2.0) + pad_sec + extra_pre
    total_post = (duration / 2.0) + pad_sec + extra_post
    start_time = max(0.0, center_ts - total_pre)
    end_time = min(video_duration, center_ts + total_post)
    if start_time >= end_time:
        raise ValueError("Computed clip window is empty. Adjust timestamp or padding.")
    return start_time, end_time


def next_output_index(character: str, move: str, out_dir: str = OUTPUT_DIR) -> int:
    """
    Scan existing files for the move and return the next sequential index.
    """
    char_dir = os.path.join(out_dir, sanitize_label(character))
    move_dir = os.path.join(char_dir, sanitize_label(move))
    if not os.path.isdir(move_dir):
        return 1
    prefix = f"{sanitize_label(character)}_{sanitize_label(move)}_"
    pattern = re.compile(rf"{re.escape(prefix)}(\d+)\.mp4$", re.IGNORECASE)
    max_idx = 0
    for filename in os.listdir(move_dir):
        match = pattern.match(filename)
        if match:
            max_idx = max(max_idx, int(match.group(1)))
    return max_idx + 1


def manual_trim_flow():
    print("=== Manual Clip Extraction ===")
    video_name = input("Enter video filename (must be in 'videos' folder): ").strip()
    start_str = input("Enter start time (seconds or mm:ss): ").strip()
    end_str = input("Enter end time (seconds or mm:ss): ").strip()

    try:
        start = parse_time(start_str)
        end = parse_time(end_str)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    trim_video(video_name, start, end)


def move_extractor_flow():
    print("=== Move Extractor ===")
    video_name = input("Enter video filename (in 'videos' folder): ").strip()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, "videos", video_name)

    if not os.path.isfile(input_path):
        print(f"Error: {video_name} not found in 'videos' folder.")
        return

    frame_data = load_frame_data(FRAME_DATA_PATH)

    with VideoFileClip(input_path) as clip:
        duration = clip.duration
        print(f"Loaded video ({duration:.2f}s).")
        character = ""
        while not character:
            character = input("Character: ").strip()
            if not character:
                print("Character name is required.")
        character = match_character_name(character, frame_data)

        announce_move_options(character, frame_data)

        while True:
            move = input(f"Move for {character}: ").strip()
            if not move:
                continue
            move_lower = move.lower()
            if move_lower == "done":
                print("Exiting move extractor.")
                break
            if move_lower == "changechar":
                character = ""
                while not character:
                    character = input("Character: ").strip()
                    if not character:
                        print("Character name is required.")
                character = match_character_name(character, frame_data)
                announce_move_options(character, frame_data)
                continue

            move = match_move_name(character, move, frame_data)
            print(
                f"Logging timestamps for {character} - {move}. "
                "Press ENTER with no input to choose another move."
            )
            while True:
                ts_input = input(
                    "Timestamp of move (seconds or mm:ss). "
                    "Press ENTER to choose a new move: "
                ).strip()
                if ts_input == "":
                    break
                try:
                    center = parse_time_to_seconds(ts_input)
                except ValueError as exc:
                    print(f"Error: {exc}")
                    continue

                if center >= duration:
                    print("Timestamp is beyond video duration. Try again.")
                    continue

                try:
                    character = match_character_name(character, frame_data)
                    move = match_move_name(character, move, frame_data)
                    start_time, end_time = get_clip_range(
                        character,
                        move,
                        center,
                        duration,
                        frame_data,
                        FRAME_DATA_PATH,
                    )
                except ValueError as exc:
                    print(f"Error: {exc}")
                    continue

                save_move_clip(
                    clip,
                    character,
                    move,
                    video_name,
                    center,
                    start_time,
                    end_time,
                )


def announce_move_options(character: str, frame_data: Dict[str, Dict[str, int]]) -> None:
    moves = frame_data.get(character, {})
    if moves:
        move_list = ", ".join(sorted(moves.keys()))
        print(
            f"Enter move names for {character} (known moves: {move_list}). "
            "Type 'done' when finished or 'changechar' to pick a new character."
        )
    else:
        print(
            f"No stored moves yet for {character}. "
            "Type the move name to add one, 'done' to exit, or 'changechar' to pick a new character."
        )


def save_move_clip(
    clip: VideoFileClip,
    character: str,
    move: str,
    video_name: str,
    center_seconds: float,
    start_time: float,
    end_time: float,
):
    """Write the requested move clip to disk with structured naming."""
    char_dir = os.path.join(OUTPUT_DIR, sanitize_label(character))
    move_dir = os.path.join(char_dir, sanitize_label(move))
    os.makedirs(move_dir, exist_ok=True)

    index = next_output_index(character, move)
    filename = f"{sanitize_label(character)}_{sanitize_label(move)}_{index:03d}.mp4"
    output_path = os.path.join(move_dir, filename)
    print(f"Writing: {output_path}")
    trimmed = clip.subclip(start_time, end_time)
    trimmed.write_videofile(output_path, codec="libx264", audio_codec="aac")
    trimmed.close()


def trim_video(video_name, start_time, end_time, output_folder=OUTPUT_DIR):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, "videos", video_name)

    if not os.path.isfile(input_path):
        print(f"Error: {video_name} not found in 'videos' folder.")
        return

    os.makedirs(output_folder, exist_ok=True)

    name, ext = os.path.splitext(video_name)
    output_path = os.path.join(output_folder, f"{name}_trimmed{ext}")

    with VideoFileClip(input_path) as clip:
        if start_time >= clip.duration:
            print("Error: start time is beyond video duration.")
            return
        if end_time <= start_time:
            print("Error: end time must be greater than start time.")
            return
        end_time = min(end_time, clip.duration)
        trimmed = clip.subclip(start_time, end_time)
        trimmed.write_videofile(output_path, codec="libx264", audio_codec="aac")

    print(f"Trimmed video saved at: {output_path}")


def main():
    while True:
        print("=== Command Line Video Editor ===")
        print("1) Manual Clip Extraction")
        print("2) Move extractor (looping, data collection)")
        print("3) Exit")
        choice = input("Select option: ").strip()
        if choice == "1":
            manual_trim_flow()
        elif choice == "2":
            move_extractor_flow()
        elif choice == "3":
            print("Goodbye.")
            break
        else:
            print("Invalid choice. Please select 1, 2, or 3.")


if __name__ == "__main__":
    main()
