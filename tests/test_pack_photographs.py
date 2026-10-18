from pathlib import Path

from arrabida_dataset.pack_photographs import Photo, _frame_orders, _zip_date, record_name


def photo(**changes):
    return Photo(**{
        "campaign": "september", "stratum": "shallow", "transect": 2, "quadrat": None, "source": Path("x"),
        "relative_path": "7m_T2/DSC1.JPG", "format": "jpeg", "stem": "DSC1",
        "datetime_original": "2026-09-02T11:02:13", "time_offset": "+01:00", "camera": "SONY ILCE-7M4",
        "lens": "", "width": 1, "height": 1, "size": 1, **changes,
    })


def test_july_files_are_named_by_quadrat():
    assert record_name(photo(campaign="july", stratum="deep", transect=1, quadrat=3), 3) == "photo_july-deep-T1-Q3.jpg"


def test_september_raw_files_share_their_jpeg_name():
    assert record_name(photo(format="arw"), 2) == "photo_september-shallow-T2-F2.arw"


def test_september_frames_are_numbered_by_capture_time():
    later = photo(stem="DSC1", datetime_original="2026-09-02T11:05:00")
    earlier = photo(stem="DSC9", datetime_original="2026-09-02T11:01:00")
    raw = photo(stem="DSC1", format="arw", datetime_original="2026-09-02T11:05:00")
    orders = _frame_orders([later, earlier, raw])
    assert orders[("september", "shallow", 2, "DSC9")] == 1
    assert orders[("september", "shallow", 2, "DSC1")] == 2


def test_archive_members_carry_the_capture_time():
    assert _zip_date("2026-07-08T13:27:05") == (2026, 7, 8, 13, 27, 5)
