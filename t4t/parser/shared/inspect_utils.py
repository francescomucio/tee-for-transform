"""
Utility functions for frame inspection and caller information extraction.
"""

import inspect
import os
from collections.abc import Iterator


def get_caller_file_info(frames_up: int = 2) -> tuple[str | None, bool]:
    """
    Get caller file path and whether it's being run as __main__.

    This function inspects the call stack to find the caller's file information.
    It's commonly used in dataclass __post_init__ methods where we need to go
    up 2 frames: __post_init__ -> generated __init__ -> actual caller.

    Args:
        frames_up: Number of frames to go up (default 2 for dataclass __post_init__)

    Returns:
        Tuple of (file_path, is_main) where:
        - file_path: Absolute path to the caller's file, or None if not found
        - is_main: True if the caller is being run as __main__, False otherwise
    """
    frame = inspect.currentframe()
    if not frame:
        return None, False

    # Go up the specified number of frames
    caller_frame = frame
    for _ in range(frames_up):
        if caller_frame.f_back:
            caller_frame = caller_frame.f_back
        else:
            # If we can't go up enough frames, try the last available frame
            break

    caller_globals = caller_frame.f_globals
    file_path = caller_globals.get("__file__")
    is_main = caller_globals.get("__name__") == "__main__"

    if file_path:
        file_path = os.path.abspath(file_path)

    return file_path, is_main


def get_caller_file_path(frames_up: int = 2) -> str | None:
    """
    Get caller file path only (convenience function when is_main is not needed).

    Args:
        frames_up: Number of frames to go up (default 2)

    Returns:
        Absolute path to the caller's file, or None if not found
    """
    file_path, _ = get_caller_file_info(frames_up)
    return file_path


# Maximum number of frames to walk when searching for caller information
MAX_FRAME_WALK_DEPTH = 5


def _iter_frames(
    start_frame: inspect.FrameType | None, max_frames: int
) -> Iterator[inspect.FrameType]:
    """
    Generator that yields frames walking up the call stack.

    Args:
        start_frame: Starting frame (usually current frame)
        max_frames: Maximum number of frames to walk up

    Yields:
        Frame objects from the call stack
    """
    frame = start_frame
    for _ in range(max_frames):
        if frame and frame.f_back:
            frame = frame.f_back
            yield frame
        else:
            break


def get_caller_file_and_main(max_frames: int = MAX_FRAME_WALK_DEPTH) -> tuple[str | None, bool]:
    """
    Get caller file path and __main__ status using frame-walking with __tee_file_path__ support.

    This function walks up the frame stack to find the caller's file information,
    prioritizing __tee_file_path__ (injected by the parser for executed modules) over __file__.
    This is more reliable than get_caller_file_info() when dealing with modules executed
    by the parser, as it can detect the injected __tee_file_path__ variable.

    Args:
        max_frames: Maximum number of frames to walk up (default: MAX_FRAME_WALK_DEPTH)

    Returns:
        Tuple of (file_path, is_main) where:
        - file_path: Absolute path to the caller's file, or None if not found
        - is_main: True if the caller is being run as __main__, False otherwise
    """
    start_frame = inspect.currentframe()
    if not start_frame:
        return None, False

    caller_file: str | None = None
    caller_main = False

    # Walk up the frame stack to find the module's __tee_file_path__ or __file__
    current_frame = start_frame
    for _ in range(max_frames):
        if current_frame and current_frame.f_back:
            current_frame = current_frame.f_back
            frame_globals = current_frame.f_globals
            # Check for __tee_file_path__ first (most reliable, injected by parser)
            if "__tee_file_path__" in frame_globals:
                caller_file = frame_globals["__tee_file_path__"]
                caller_main = frame_globals.get("__name__") == "__main__"
                break
            # Fall back to __file__
            if "__file__" in frame_globals:
                caller_file = frame_globals["__file__"]
                caller_main = frame_globals.get("__name__") == "__main__"
                # Don't break here - keep looking for __tee_file_path__ in higher frames
        else:
            break

    # If still not found, use get_caller_file_info as fallback
    if not caller_file:
        caller_file, caller_main = get_caller_file_info(frames_up=2)

    # Ensure absolute path
    if caller_file:
        caller_file = os.path.abspath(caller_file)

    # If still not found but we're in __main__, try to get file from sys.argv[0]
    # This handles the case when running a file directly
    if not caller_file and caller_main:
        import sys

        if sys.argv and sys.argv[0] and sys.argv[0] != "-c":
            potential_file = os.path.abspath(sys.argv[0])
            if os.path.isfile(potential_file):
                return potential_file, True

    return caller_file, caller_main
