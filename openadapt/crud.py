"""Implements basic CRUD operations for interacting with a database.

Module: crud.py
"""

from typing import Any

from loguru import logger
import sqlalchemy as sa

from openadapt import config
from openadapt.db import BaseModel, Session
from openadapt.models import (
    ActionEvent,
    MemoryStat,
    PerformanceStat,
    Recording,
    Screenshot,
    WindowEvent,
)

BATCH_SIZE = 1

db = Session()
action_events = []
screenshots = []
window_events = []
performance_stats = []
memory_stats = []


def _insert(
    event_data: dict[str, Any],
    table: sa.Table,
    buffer: list[dict[str, Any]] | None = None,
) -> sa.engine.Result | None:
    """Insert using Core API for improved performance (no rows are returned).

    Args:
        event_data (dict): The event data to be inserted.
        table (sa.Table): The SQLAlchemy table to insert the data into.
        buffer (list, optional): A buffer list to store the inserted objects
            before committing. Defaults to None.

    Returns:
        sa.engine.Result | None: The SQLAlchemy Result object if a buffer is
          not provided. None if a buffer is provided.
    """
    db_obj = {column.name: None for column in table.__table__.columns}
    for key in db_obj:
        if key in event_data:
            val = event_data[key]
            db_obj[key] = val
            del event_data[key]

    # make sure all event data was saved
    assert not event_data, event_data

    if buffer is not None:
        buffer.append(db_obj)

    if buffer is None or len(buffer) >= BATCH_SIZE:
        to_insert = buffer or [db_obj]
        result = db.execute(sa.insert(table), to_insert)
        db.commit()
        if buffer:
            buffer.clear()
        # Note: this does not contain the inserted row(s)
        return result


def insert_action_event(
    recording_timestamp: int, event_timestamp: int, event_data: dict[str, Any]
) -> None:
    """Insert an action event into the database.

    Args:
        recording_timestamp (int): The timestamp of the recording.
        event_timestamp (int): The timestamp of the event.
        event_data (dict): The data of the event.
    """
    event_data = {
        **event_data,
        "timestamp": event_timestamp,
        "recording_timestamp": recording_timestamp,
    }
    _insert(event_data, ActionEvent, action_events)


def insert_screenshot(
    recording_timestamp: int, event_timestamp: int, event_data: dict[str, Any]
) -> None:
    """Insert a screenshot into the database.

    Args:
        recording_timestamp (int): The timestamp of the recording.
        event_timestamp (int): The timestamp of the event.
        event_data (dict): The data of the event.
    """
    event_data = {
        **event_data,
        "timestamp": event_timestamp,
        "recording_timestamp": recording_timestamp,
    }
    _insert(event_data, Screenshot, screenshots)


def insert_window_event(
    recording_timestamp: int,
    event_timestamp: int,
    event_data: dict[str, Any],
) -> None:
    """Insert a window event into the database.

    Args:
        recording_timestamp (int): The timestamp of the recording.
        event_timestamp (int): The timestamp of the event.
        event_data (dict): The data of the event.
    """
    event_data = {
        **event_data,
        "timestamp": event_timestamp,
        "recording_timestamp": recording_timestamp,
    }
    _insert(event_data, WindowEvent, window_events)


def insert_perf_stat(
    recording_timestamp: int,
    event_type: str,
    start_time: float,
    end_time: float,
) -> None:
    """Insert an event performance stat into the database.

    Args:
        recording_timestamp (int): The timestamp of the recording.
        event_type (str): The type of the event.
        start_time (float): The start time of the event.
        end_time (float): The end time of the event.
    """
    event_perf_stat = {
        "recording_timestamp": recording_timestamp,
        "event_type": event_type,
        "start_time": start_time,
        "end_time": end_time,
    }
    _insert(event_perf_stat, PerformanceStat, performance_stats)


def get_perf_stats(recording_timestamp: int) -> list[PerformanceStat]:
    """Get performance stats for a given recording.

    Args:
        recording_timestamp (int): The timestamp of the recording.

    Returns:
        list[PerformanceStat]: A list of performance stats for the recording.
    """
    return (
        db.query(PerformanceStat)
        .filter(PerformanceStat.recording_timestamp == recording_timestamp)
        .order_by(PerformanceStat.start_time)
        .all()
    )


def insert_memory_stat(
    recording_timestamp: int, memory_usage_bytes: int, timestamp: int
) -> None:
    """Insert memory stat into db."""
    memory_stat = {
        "recording_timestamp": recording_timestamp,
        "memory_usage_bytes": memory_usage_bytes,
        "timestamp": timestamp,
    }
    _insert(memory_stat, MemoryStat, memory_stats)


def get_memory_stats(recording_timestamp: int) -> None:
    """Return memory stats for a given recording."""
    return (
        db.query(MemoryStat)
        .filter(MemoryStat.recording_timestamp == recording_timestamp)
        .order_by(MemoryStat.timestamp)
        .all()
    )


def insert_recording(recording_data: Recording) -> Recording:
    """Insert the recording into to the db."""
    db_obj = Recording(**recording_data)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def get_latest_recording() -> Recording:
    """Get the latest recording.

    Returns:
        Recording: The latest recording object.
    """
    return db.query(Recording).order_by(sa.desc(Recording.timestamp)).limit(1).first()


def get_recording(timestamp: int) -> Recording:
    """Get a recording by timestamp.

    Args:
        timestamp (int): The timestamp of the recording.

    Returns:
        Recording: The recording object.
    """
    return db.query(Recording).filter(Recording.timestamp == timestamp).first()


def _get(table: BaseModel, recording_timestamp: int) -> list[BaseModel]:
    """Retrieve records from the database table based on the recording timestamp.

    Args:
        table (BaseModel): The database table to query.
        recording_timestamp (int): The recording timestamp to filter the records.

    Returns:
        list[BaseModel]: A list of records retrieved from the database table,
          ordered by timestamp.
    """
    return (
        db.query(table)
        .filter(table.recording_timestamp == recording_timestamp)
        .order_by(table.timestamp)
        .all()
    )


def get_action_events(recording: Recording) -> list[ActionEvent]:
    """Get action events for a given recording.

    Args:
        recording (Recording): The recording object.

    Returns:
        list[ActionEvent]: A list of action events for the recording.
    """
    assert recording, "Invalid recording."
    action_events = _get(ActionEvent, recording.timestamp)
    # filter out stop sequences listed in STOP_SEQUENCES and Ctrl + C
    filter_stop_sequences(action_events)
    return action_events


def filter_stop_sequences(action_events: list[ActionEvent]) -> None:
    """Filter stop sequences.

    Args:
        List[ActionEvent]: A list of action events for the recording.

    Returns:
        None
    """
    # check for ctrl c first
    # TODO: want to handle sequences like ctrl c the same way as normal sequences
    if len(action_events) >= 2:
        if (
            action_events[-1].canonical_key_char == "c"
            and action_events[-2].canonical_key_name == "ctrl"
        ):
            # remove ctrl c
            # ctrl c must be held down at same time, so no release event
            action_events.pop()
            action_events.pop()
            return

    # create list of indices for sequence detection
    # one index for each stop sequence in STOP_SEQUENCES
    # start from the back of the sequence
    stop_sequence_indices = [len(sequence) - 1 for sequence in config.STOP_SEQUENCES]

    # index of sequence to remove, -1 if none found
    sequence_to_remove = -1
    # number of events to remove
    num_to_remove = 0

    for i in range(0, len(config.STOP_SEQUENCES)):
        # iterate backwards through list of action events
        for j in range(len(action_events) - 1, -1, -1):
            # never go past 1st action event, so if a sequence is longer than
            # len(action_events), it can't have been in the recording
            if (
                action_events[j].canonical_key_char
                == config.STOP_SEQUENCES[i][stop_sequence_indices[i]]
                or action_events[j].canonical_key_name
                == config.STOP_SEQUENCES[i][stop_sequence_indices[i]]
            ) and action_events[j].name == "press":
                # for press events, compare the characters
                stop_sequence_indices[i] -= 1
                num_to_remove += 1
            elif action_events[j].name == "release" and (
                action_events[j].canonical_key_char in config.STOP_SEQUENCES[i]
                or action_events[j].canonical_key_name in config.STOP_SEQUENCES[i]
            ):
                # can consider any release event with any sequence char as
                # part of the sequence
                num_to_remove += 1
            else:
                # not part of the sequence, so exit inner loop
                break

        if stop_sequence_indices[i] == -1:
            # completed whole sequence, so set sequence_to_remove to
            # current sequence and exit outer loop
            sequence_to_remove = i
            break

    if sequence_to_remove != -1:
        # remove that sequence
        for _ in range(0, num_to_remove):
            action_events.pop()


def save_screenshot_diff(screenshots: list[Screenshot]) -> list[Screenshot]:
    """Save screenshot diff data to the database. The diff data is the difference
    between two consecutive screenshots.

    Args:
        screenshots (list[Screenshot]): A list of screenshots.

    Returns:
        list[Screenshot]: A list of screenshots with diff data saved to the db."""
    data_updated = False
    logger.info("verifying diffs for screenshots...")

    for screenshot in screenshots:
        if not screenshot.prev:
            continue
        if not screenshot.png_diff_data:
            screenshot.png_diff_data = screenshot.convert_png_to_binary(screenshot.diff)
            data_updated = True
        if not screenshot.png_diff_mask_data:
            screenshot.png_diff_mask_data = screenshot.convert_png_to_binary(
                screenshot.diff_mask
            )
            data_updated = True

    if data_updated:
        logger.info("saving screenshot diff data to db...")
        db.bulk_save_objects(screenshots)
        db.commit()

    return screenshots


def get_screenshots(recording: Recording) -> list[Screenshot]:
    """Get screenshots for a given recording.

    Args:
        recording (Recording): The recording object.

    Returns:
        list[Screenshot]: A list of screenshots for the recording.
    """
    screenshots = _get(Screenshot, recording.timestamp)

    for prev, cur in zip(screenshots, screenshots[1:]):
        cur.prev = prev
    if screenshots:
        screenshots[0].prev = screenshots[0]

    if config.SAVE_SCREENSHOT_DIFF:
        screenshots = save_screenshot_diff(screenshots)
    return screenshots


def get_window_events(recording: Recording) -> list[WindowEvent]:
    """Get window events for a given recording.

    Args:
        recording (Recording): The recording object.

    Returns:
        list[WindowEvent]: A list of window events for the recording.
    """
    return _get(WindowEvent, recording.timestamp)
