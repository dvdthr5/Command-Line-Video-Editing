Take the existing `editingScript.py` command-line trimmer and extend it to support **move-based clip extraction** for Super Smash Bros. Ultimate. This does **not** train a model. It only helps generate datasets by clipping moves from a given video using known frame counts.

## Project scope
Goal: build a dataset of labeled move clips to train a recognition model later. **Do not implement model training or automated detection now.** In this phase we only implement efficient, human-guided data collection: fast extraction of clips around timestamps using known frame counts.

Each extracted clip should be automatically saved, labeled, and sorted into organized folders:
`output/<Character>/<Move>/` with filenames like `<Character>_<Move>_<timestamp>_<index>.mp4`. 
This ensures clean dataset structure for later model training.

If the destination folders do not exist, the program must automatically create them. If they already exist, simply add new clips to the existing folders. Each character’s folder under `output/` should contain one subfolder per move, allowing clips to accumulate over time as more data is collected.

## Objectives
1) Keep the current manual trim mode intact.
2) Add a new **Move Extractor** mode that:
   - Prompts for:
     - **Character** (e.g., "Donkey Kong")
     - **Move** (e.g., "Forward Smash")
     - **Timestamp** where the move occurs (accept seconds or mm:ss)
     - **Input video filename** (from the `videos/` folder)
   - Computes the clip’s start and end times automatically from the move’s **frame count** at 60 FPS.
   - Writes the result into `output/` with a descriptive filename.

## Data files
Create a **second JSON file** named `frame_data.json` alongside the script to hold frame counts per character. Example content:

```json
{
  "Donkey Kong": {
    "Jab 1": 24,
    "Jab 2": 31,
    "Forward Tilt": 34,
    "Up Tilt": 38,
    "Down Tilt": 24,
    "Dash Attack": 34,
    "Forward Smash": 55,
    "Up Smash": 49,
    "Down Smash": 55,
    "Neutral Air": 38,
    "Forward Air": 55,
    "Back Air": 31,
    "Up Air": 37,
    "Down Air": 54,
    "Neutral B (Giant Punch)": 62,
    "Side B (Headbutt)": 62,
    "Up B (Spinning Kong)": 104,
    "Up B (Air)": 38,
    "Down B (Hand Slap)": 46
  }
}
```

Notes:
- 60 frames = 1.0 second. Convert frames → seconds with `frames / 60.0`.
- Allow easy extension by adding new characters and moves in the same structure.
- If a character or move is missing, prompt the user to enter a frame count, then **optionally append** it back to `frame_data.json`.
- Automatically create subdirectories for each character and move if they do not exist before writing clips.
- If `frame_data.json` does not contain data for a selected character or move, prompt the user to input the missing frame count and automatically append it to the JSON file before continuing.

## CLI Behavior
Add a top-level menu:
```
=== Command Line Video Editor ===
1) Manual trim (existing)
2) Move extractor (looping, data collection)
Select option: 
```

For **Move extractor** flow:
1. Prompt once: `Character:` (persist this until user changes it).
2. Loop over **moves**:
   a. Prompt: `Move:` (e.g., Forward Smash). Enter `done` to finish the session, or `changechar` to select a new character and continue.
   b. For the selected move, repeatedly prompt **timestamps** until user signals next move:
      - Prompt: `Timestamp of move (seconds or mm:ss). Press ENTER with no input to go to next move:`
      - Each non-empty timestamp immediately creates a clip using frame data.
      - Empty input (`""`) ends the timestamp loop for this move and returns to step 2a.
3. At any time, if the character/move is missing from `frame_data.json`, prompt for the frame count and optionally persist it back to the JSON.
5. For each timestamp entry:
   - Load `frame_data.json`, read `frames = frame_data[character][move]` (prompt if missing).
   - Compute duration seconds: `dur = frames / 60.0`.
   - Compute symmetric window around timestamp with padding:
     * Default: `pre = dur / 2`, `post = dur / 2`
     * Add fixed frame padding on each side (20–25 frames by default).
       - Example: `frame_pad = 25`, so `pad_sec = frame_pad / 60.0`.
       - Final window:
         - `start_time = max(0, center - pre - pad_sec)`
         - `end_time = min(video_duration, center + post + pad_sec)`
     * Clamp all times to `[0, clip.duration]`.
     * Padding constants (`frame_pad`, `extra_pre`, `extra_post`) should be easy to configure at the top of the file.
   - Derive:
     * `center = parsed_timestamp`
     * `start_time = max(0, center - pre - pad_sec)`
     * `end_time   = min(video_duration, center + post + pad_sec)`
   - Trim using MoviePy 1.0.3:
     * `from moviepy.editor import VideoFileClip`
     * `clip.subclip(start_time, end_time).write_videofile(...)`
   - Output naming:
     * `output/<Character>/<Move>/<Character>_<Move>_<HHMMSS or seconds>_<index>.mp4`
       - Example: `output/DonkeyKong/ForwardSmash/DonkeyKong_ForwardSmash_00412_001.mp4` (auto-increment per move)

## Functions to add
Implement the following helpers in `editingScript.py`:

```python
def load_frame_data(path="frame_data.json"):
    """Return dict loaded from JSON. If missing, create a minimal empty dict and return {}."""

def save_frame_data(data, path="frame_data.json"):
    """Write dict back to JSON (pretty-printed)."""

def parse_time_to_seconds(s: str) -> float:
    """
    Accept 'ss' or 'mm:ss'. Return float seconds.
    Reuse existing parse_time if present. Validate digit-only segments.
    """

def get_clip_range(character: str, move: str, center_ts: float, video_duration: float, frame_data: dict, fps: float = 60.0, extra_pre: float = 0.10, extra_post: float = 0.10):
    """
    Look up frames for (character, move). Compute duration = frames / fps.
    Use symmetric window: pre = post = duration / 2. Add padding.
    Clamp to [0, video_duration]. Return (start_time, end_time).
    If not found, prompt for manual frame count, update frame_data, and retry.
    """
```

```python
def next_output_index(character: str, move: str, out_dir: str) -> int:
    """
    Scan `out_dir` for files matching the pattern and return the next sequence index for that (character, move).
    """
```

## Error handling
- If `frame_data.json` is missing, create it with `{}` and prompt for frames on first use.
- If character not found: prompt to add it or abort.
- If move not found under character: prompt to add it or abort.
- If timestamp ≥ video duration: print error and reprompt.
- If computed `start_time >= end_time`: print error and reprompt.

## Implementation constraints
- Assume **MoviePy 1.0.3** is installed. Use:
  ```python
  from moviepy.editor import VideoFileClip
  ```
  and:
  ```python
  trimmed = clip.subclip(start_time, end_time)
  trimmed.write_videofile(output_path, codec="libx264", audio_codec="aac")
  ```
- Preserve existing `videos/` source folder and `output/` target folder.
- Reuse existing parsing and validation where possible.

## Example session
```
=== Command Line Video Editor ===
1) Manual trim
2) Move extractor (looping, data collection)
Select option: 2
Enter video filename (in 'videos' folder): dk_set1_game1.mov
Character: Donkey Kong

Move: Forward Smash
Timestamp of move (seconds or mm:ss). Press ENTER to go to next move: 4:12
Loaded frames: 55 -> 0.9167s total
Writing: output/DonkeyKong/ForwardSmash/DonkeyKong_ForwardSmash_00412_001.mp4
Timestamp of move (seconds or mm:ss). Press ENTER to go to next move: 7:03
Writing: output/DonkeyKong/ForwardSmash/DonkeyKong_ForwardSmash_00703_002.mp4
Timestamp of move (seconds or mm:ss). Press ENTER to go to next move:

Move: Back Air
Timestamp of move (seconds or mm:ss). Press ENTER to go to next move: 5:21
Loaded frames: 31 -> 0.5167s total
Writing: output/DonkeyKong/BackAir/DonkeyKong_BackAir_00521_001.mp4
Timestamp of move (seconds or mm:ss). Press ENTER to go to next move:

Move: changechar
Character: Mario
Move: Up Smash
Timestamp of move (seconds or mm:ss). Press ENTER to go to next move: 3:44
Writing: output/Mario/UpSmash/Mario_UpSmash_00344_001.mp4
Timestamp of move (seconds or mm:ss). Press ENTER to go to next move:

Move: done
Done.
```
