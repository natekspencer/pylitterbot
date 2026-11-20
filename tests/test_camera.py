"""Test camera module."""

# pylint: disable=protected-access
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from aiohttp import ClientConnectionError, ClientResponseError, RequestInfo, WSMsgType
from aiointercept import aiointercept
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from pylitterbot import Account, camera
from pylitterbot.camera import (
    CAMERA_CANVAS_FRONT,
    CAMERA_CANVAS_GLOBE,
    CAMERA_INVENTORY_API,
    CameraClient,
    CameraSession,
    CameraSignalingRelay,
    CameraStream,
    VideoChunk,
    VideoClip,
    VideoPlayback,
    _decode_sdp,
    _finish_before_cancelling,
    _parse_signaling_message,
    local_timezone_name,
)
from pylitterbot.exceptions import (
    CameraNotAvailableException,
    CameraStreamException,
    InvalidCommandException,
)
from pylitterbot.robot.litterrobot5 import LitterRobot5
from pylitterbot.utils import encode, utcnow

from .common import (
    CAMERA_DEVICE_ID,
    CAMERA_EVENTS_RESPONSE,
    CAMERA_SESSION_RESPONSE,
    CAMERA_VIDEO_SETTINGS_RESPONSE,
    CAMERA_VIDEOS_RESPONSE,
    LITTER_ROBOT_5_DATA,
    LITTER_ROBOT_5_PRO_DATA,
)


class TestCameraSession:
    """Tests for CameraSession dataclass."""

    def test_from_response(self) -> None:
        """Test CameraSession creation from API response."""
        session = CameraSession.from_response(CAMERA_SESSION_RESPONSE)
        assert session.session_id == "test-session-id-1234"
        assert session.session_token == "test-session-token-abcdef"
        assert session.session_expiration is not None
        assert session.signaling_url == "wss://watford.ienso-dev.com/api/signaling"
        assert len(session.turn_servers) == 1
        assert session.turn_servers[0]["username"] == "test-session-id-1234"
        assert session.turn_servers[0]["password"] == "test-turn-password"
        assert session.raw == CAMERA_SESSION_RESPONSE

    def test_from_response_missing_fields(self) -> None:
        """Test CameraSession with minimal/empty data."""
        session = CameraSession.from_response({})
        assert session.session_id == ""
        assert session.session_token == ""
        assert session.session_expiration is None
        assert session.turn_servers == []

    def test_from_response_dict_turn_creds(self) -> None:
        """Test CameraSession when turnCredentials is a dict (not list)."""
        data = {
            **CAMERA_SESSION_RESPONSE,
            "turnServer": None,
            "turnCredentials": {
                "urls": ["turn:example.com:443"],
                "username": "u",
                "credential": "c",
            },
        }
        session = CameraSession.from_response(data)
        assert len(session.turn_servers) == 1
        assert session.turn_servers[0]["username"] == "u"

    def test_from_response_ice_servers_key(self) -> None:
        """Test CameraSession when iceServers is used instead of turnServer."""
        data = {
            "sessionId": "s1",
            "sessionToken": "t1",
            "iceServers": [
                {"urls": "turn:ice.example.com", "username": "u", "credential": "c"}
            ],
        }
        session = CameraSession.from_response(data)
        assert len(session.turn_servers) == 1

    def test_from_response_fallback_signaling_url(self) -> None:
        """Test CameraSession builds signaling URL when not provided."""
        data = {
            "sessionId": "s1",
            "sessionToken": "t1",
        }
        session = CameraSession.from_response(data)
        assert "wss://" in session.signaling_url
        assert "signaling" in session.signaling_url


class TestVideoClip:
    """Tests for VideoClip dataclass."""

    def test_from_response(self) -> None:
        """Test VideoClip creation from API response."""
        clip = VideoClip.from_response(CAMERA_VIDEOS_RESPONSE[0])
        assert clip.id == "12345"
        assert clip.thumbnail_url == "https://example.com/thumb1.jpg"
        assert clip.event_type == "PET_VISIT"
        assert clip.created_at is not None
        assert clip.raw == CAMERA_VIDEOS_RESPONSE[0]

    def test_from_response_second_video(self) -> None:
        """Test VideoClip creation from second response entry."""
        clip = VideoClip.from_response(CAMERA_VIDEOS_RESPONSE[1])
        assert clip.id == "12346"
        assert clip.event_type == "cat_detected"
        assert clip.thumbnail_url == "https://example.com/thumb2.jpg"

    def test_from_response_empty(self) -> None:
        """Test VideoClip with empty response."""
        clip = VideoClip.from_response({})
        assert clip.id == ""
        assert clip.thumbnail_url is None
        assert clip.event_type is None
        assert clip.created_at is None


class TestVideoPlayback:
    """Tests for VideoPlayback dataclass."""

    def test_cookie_header(self) -> None:
        """Cookies render as an HTTP Cookie header value."""
        playback = VideoPlayback(
            clip_id="12345",
            hls_url="https://cdn.example/clip.m3u8",
            cookies={"CloudFront-Policy": "abc", "CloudFront-Signature": "def"},
        )
        assert playback.cookie_header == (
            "CloudFront-Policy=abc; CloudFront-Signature=def"
        )

    def test_cookie_header_empty(self) -> None:
        """No cookies yields an empty Cookie header."""
        playback = VideoPlayback(clip_id="1", hls_url=None, cookies={})
        assert playback.cookie_header == ""

    def test_chunks(self) -> None:
        """Chunks are parsed in order; malformed entries are skipped."""
        playback = VideoPlayback(
            clip_id="1",
            hls_url=None,
            cookies={},
            raw={
                "chunks": [
                    {"id": 1, "downloadUrl": "https://s3.example/a.mp4?sig=1"},
                    {"id": 2},
                    "bogus",
                    {"id": 3, "downloadUrl": "https://s3.example/b.mp4?sig=2"},
                ]
            },
        )
        assert playback.chunks == [
            VideoChunk(id="1", download_url="https://s3.example/a.mp4?sig=1"),
            VideoChunk(id="3", download_url="https://s3.example/b.mp4?sig=2"),
        ]

    def test_chunks_missing(self) -> None:
        """No chunks key yields an empty list."""
        playback = VideoPlayback(clip_id="1", hls_url=None, cookies={})
        assert playback.chunks == []


class TestCameraClient:
    """Tests for CameraClient REST API calls."""

    async def test_generate_session(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test generating a camera session."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
        )
        session = await client.generate_session()
        assert isinstance(session, CameraSession)
        assert session.session_id == "test-session-id-1234"
        assert session.session_token == "test-session-token-abcdef"

        await mock_account.disconnect()

    async def test_get_video_settings(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test fetching video settings."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        settings = await client.get_video_settings()
        assert settings == CAMERA_VIDEO_SETTINGS_RESPONSE["reportedSettings"][0]["data"]

        await mock_account.disconnect()

    async def test_get_audio_settings(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test fetching audio settings."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        settings = await client.get_audio_settings()
        assert settings is not None
        assert settings["audio_in"]["global"]["mute"] is True

        await mock_account.disconnect()

    async def test_set_camera_canvas(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test setting camera canvas."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        result = await client.set_camera_canvas(CAMERA_CANVAS_FRONT)
        assert result is True

        await mock_account.disconnect()

    async def test_set_audio_enabled(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test setting audio enabled."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        result = await client.set_audio_enabled(True)
        assert result is True

        await mock_account.disconnect()

    async def test_get_camera_info(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test fetching camera info."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        info = await client.get_camera_info()
        assert info is not None
        assert info["serial"] == CAMERA_DEVICE_ID

        await mock_account.disconnect()

    async def test_get_camera_status(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test fetching the camera connection status."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        assert await client.get_camera_status() == "ONLINE"

        await mock_account.disconnect()

    async def test_get_camera_canvas(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test reading the reported live-view canvas."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        assert await client.get_camera_canvas() == CAMERA_CANVAS_FRONT

        await mock_account.disconnect()

    async def test_validate_device_ownership(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test validating camera ownership (empty 200 response)."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        assert await client.validate_device_ownership() is True

        await mock_account.disconnect()

    async def test_get_videos(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test fetching video clips."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos()
        assert len(videos) == 2
        assert isinstance(videos[0], VideoClip)
        assert videos[0].id == "12345"

        await mock_account.disconnect()

    async def test_get_videos_with_limit(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test that get_videos enforces limit client-side."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(limit=1)
        assert len(videos) == 1
        assert videos[0].id == str(CAMERA_VIDEOS_RESPONSE[0]["id"])

        await mock_account.disconnect()

    async def test_get_videos_sends_page_and_timezone_and_paginates(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Pages are requested with page/timezone until an empty page."""
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        tz = "Australia/Sydney"
        mock_aiointercept.get(
            f"{base}?page=1&timezone={tz}",
            payload=[{"id": 3, "createdAt": 30.0}, {"id": 2, "createdAt": 20.0}],
        )
        mock_aiointercept.get(
            f"{base}?page=2&timezone={tz}", payload=[{"id": 1, "createdAt": 10.0}]
        )
        mock_aiointercept.get(f"{base}?page=3&timezone={tz}", payload=[])
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(timezone=tz)
        assert [v.id for v in videos] == ["3", "2", "1"]

        await mock_account.disconnect()

    async def test_get_videos_limit_stops_paging(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """No further pages are requested once ``limit`` is reached."""
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        mock_aiointercept.get(
            f"{base}?page=1&timezone=UTC",
            payload=[{"id": 3}, {"id": 2}],
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(limit=2, timezone="UTC")
        assert [v.id for v in videos] == ["3", "2"]
        pages = [
            url.query.get("page")
            for (method, url) in mock_aiointercept.requests
            if method == "GET" and url.path.endswith("/videos")
        ]
        assert pages == ["1"]

        await mock_account.disconnect()

    async def test_get_videos_dedupes_within_a_page(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """A clip repeated within one page is kept once and doesn't use up limit."""
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        mock_aiointercept.get(
            f"{base}?page=1&timezone=UTC",
            payload=[{"id": 3}, {"id": 3}, {"id": 2}],
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(limit=2, timezone="UTC")
        assert [v.id for v in videos] == ["3", "2"]

        await mock_account.disconnect()

    async def test_get_videos_date_uses_timezone(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """A date filter is sent with the timezone it should be read in."""
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        tz = "America/Detroit"
        mock_aiointercept.get(
            f"{base}/2026-11-18?page=1&timezone={tz}", payload=[{"id": 7}]
        )
        mock_aiointercept.get(f"{base}/2026-11-18?page=2&timezone={tz}", payload=[])
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(date="2026-11-18", timezone=tz)
        assert [v.id for v in videos] == ["7"]

        await mock_account.disconnect()

    async def test_get_videos_accepts_a_date(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """A ``datetime.date`` is sent as YYYY-MM-DD."""
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        mock_aiointercept.get(
            f"{base}/2026-11-18?page=1&timezone=UTC", payload=[{"id": 7}]
        )
        mock_aiointercept.get(f"{base}/2026-11-18?page=2&timezone=UTC", payload=[])
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(date=date(2026, 11, 18), timezone="UTC")
        assert [v.id for v in videos] == ["7"]

        await mock_account.disconnect()

    async def test_get_videos_rejects_a_datetime(
        self,
        mock_account: Account,
    ) -> None:
        """A datetime is rejected rather than silently dropping its time."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        with pytest.raises(TypeError):
            await client.get_videos(date=datetime(2026, 11, 18, 12))

        await mock_account.disconnect()

    async def test_get_videos_connection_error_returns_partial(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """A connection error on a later page returns the clips gathered so far."""
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        mock_aiointercept.get(f"{base}?page=1&timezone=UTC", payload=[{"id": 3}])
        mock_aiointercept.get(
            f"{base}?page=2&timezone=UTC", exception=True, repeat=True
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(timezone="UTC")
        assert [v.id for v in videos] == ["3"]

        await mock_account.disconnect()

    async def test_get_videos_connection_error_on_first_page_raises(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """A connection error on the first page is raised."""
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        mock_aiointercept.get(
            f"{base}?page=1&timezone=UTC", exception=True, repeat=True
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        with pytest.raises(ClientConnectionError):
            await client.get_videos(timezone="UTC")

        await mock_account.disconnect()

    async def test_get_videos_uses_tz_env_over_localtime(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without a timezone, ``TZ`` is sent even when /etc/localtime differs."""
        monkeypatch.setenv("TZ", "UTC")
        monkeypatch.setattr(
            "pylitterbot.camera.os.path.realpath",
            lambda _: "/usr/share/zoneinfo/America/Detroit",
        )
        base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{CAMERA_DEVICE_ID}/videos"
        mock_aiointercept.get(f"{base}?page=1&timezone=UTC", payload=[])
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        assert await client.get_videos() == []
        timezones = [
            url.query.get("timezone")
            for (method, url) in mock_aiointercept.requests
            if method == "GET" and url.path.endswith("/videos")
        ]
        assert timezones == ["UTC"]

        await mock_account.disconnect()

    async def test_get_video_playback(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fetching signed playback details (HLS URL + CloudFront cookies)."""
        clip_id = "12345"
        mock_aiointercept.get(
            f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{clip_id}",
            payload={"id": clip_id, "hlsUrl": "https://cdn.example/clip.m3u8"},
            headers=CIMultiDict(
                [
                    ("Set-Cookie", "CloudFront-Policy=pol; Path=/"),
                    ("Set-Cookie", "CloudFront-Signature=sig; Path=/"),
                    ("Set-Cookie", "CloudFront-Key-Pair-Id=kid; Path=/"),
                    ("Set-Cookie", "session=nope; Path=/"),
                ]
            ),
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )

        async def _bearer() -> str:
            return "Bearer test-token"

        monkeypatch.setattr(mock_account.session, "get_bearer_authorization", _bearer)
        playback = await client.get_video_playback(clip_id)
        assert isinstance(playback, VideoPlayback)
        assert playback.clip_id == clip_id
        assert playback.hls_url == "https://cdn.example/clip.m3u8"
        # only CloudFront-* cookies are kept (the "session" cookie is dropped)
        assert playback.cookies == {
            "CloudFront-Policy": "pol",
            "CloudFront-Signature": "sig",
            "CloudFront-Key-Pair-Id": "kid",
        }
        assert "CloudFront-Policy=pol" in playback.cookie_header

        await mock_account.disconnect()

    async def test_download_video(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        tmp_path: Any,
    ) -> None:
        """Chunks are fetched from their presigned URLs and written in order."""
        clip_id = "12345"
        urls = [
            "https://s3.example/vid-12345/a.mp4?AWSAccessKeyId=K&Signature=a%2Bb%3D&Expires=1",
            "https://s3.example/vid-12345/b.mp4?AWSAccessKeyId=K&Signature=c%2Fd%3D&Expires=1",
        ]
        mock_aiointercept.get(
            f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{clip_id}",
            payload={
                "id": clip_id,
                "chunks": [{"id": i, "downloadUrl": u} for i, u in enumerate(urls)],
            },
        )
        mock_aiointercept.get(urls[0], body=b"chunk-a")
        mock_aiointercept.get(urls[1], body=b"chunk-b")
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        paths = await client.download_video(clip_id, tmp_path / "clips")
        assert paths is not None
        assert [p.name for p in paths] == ["12345_00.mp4", "12345_01.mp4"]
        assert [p.read_bytes() for p in paths] == [b"chunk-a", b"chunk-b"]

        await mock_account.disconnect()

    async def test_fetch_video_chunks_uses_caller_session(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Chunks go through the caller's session, without pylitterbot's auth."""
        clip_id = "12345"
        url = "https://s3.example/vid-12345/a.mp4?Signature=a%2Bb%3D"
        mock_aiointercept.get(
            f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{clip_id}",
            payload={"id": clip_id, "chunks": [{"id": 1, "downloadUrl": url}]},
        )
        mock_aiointercept.get(url, body=b"chunk-a")
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        websession = client.websession
        requested: list[str] = []
        original_get = websession.get

        def _spy_get(url: Any, **kwargs: Any) -> Any:
            requested.append(str(url))
            return original_get(url, **kwargs)

        monkeypatch.setattr(websession, "get", _spy_get)
        assert await client.fetch_video_chunks(clip_id) == [b"chunk-a"]
        assert url in requested
        chunk_requests = [
            req
            for (method, req_url), reqs in mock_aiointercept.requests.items()
            if method == "GET" and req_url.host == "s3.example"
            for req in reqs
        ]
        assert len(chunk_requests) == 1
        for header in ("Authorization", "X-Api-Key"):
            assert header not in chunk_requests[0].headers

        await mock_account.disconnect()

    @pytest.mark.parametrize("clip_id", ["../12345", "a/b", "", "/tmp/x"])
    async def test_download_video_rejects_path_like_clip_id(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        tmp_path: Any,
        clip_id: str,
    ) -> None:
        """A clip ID that isn't a plain file name is rejected before any request."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        with pytest.raises(ValueError):
            await client.download_video(clip_id, tmp_path)
        assert not any(
            url.path.startswith("/prod/v1/camera-videos")
            for (_, url) in mock_aiointercept.requests
        )

        await mock_account.disconnect()

    async def test_download_video_chunk_failure_writes_nothing(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        tmp_path: Any,
    ) -> None:
        """A failed chunk raises and leaves no partial files."""
        clip_id = "12345"
        urls = ["https://s3.example/ok.mp4", "https://s3.example/expired.mp4"]
        mock_aiointercept.get(
            f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{clip_id}",
            payload={
                "id": clip_id,
                "chunks": [{"id": i, "downloadUrl": u} for i, u in enumerate(urls)],
            },
        )
        mock_aiointercept.get(urls[0], body=b"chunk-a")
        mock_aiointercept.get(urls[1], status=403)
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        with pytest.raises(ClientResponseError):
            await client.download_video(clip_id, tmp_path / "clips")
        assert not (tmp_path / "clips").exists()

        await mock_account.disconnect()

    async def test_download_video_playback_failure_returns_none(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        tmp_path: Any,
    ) -> None:
        """If the clip details can't be fetched, nothing is downloaded."""
        clip_id = "99999"
        mock_aiointercept.get(
            f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{clip_id}",
            status=403,
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        assert await client.download_video(clip_id, tmp_path) is None

        await mock_account.disconnect()

    async def test_get_video_playback_failure_returns_none(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test that an API error yields None rather than raising."""
        clip_id = "99999"
        mock_aiointercept.get(
            f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{clip_id}",
            status=403,
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        assert await client.get_video_playback(clip_id) is None

        await mock_account.disconnect()

    async def test_get_video_playback_non_dict_returns_none(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test that an unexpected (non-object) response yields None."""
        clip_id = "88888"
        mock_aiointercept.get(
            f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{clip_id}",
            payload=["unexpected"],
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        assert await client.get_video_playback(clip_id) is None

        await mock_account.disconnect()

    async def test_get_events(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test fetching camera events."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        events = await client.get_events(limit=10)
        assert len(events) == 2
        assert events[0]["eventId"] == "evt-001"

        await mock_account.disconnect()

    async def test_get_events_with_limit(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test that get_events enforces limit client-side."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        events = await client.get_events(limit=1)
        assert len(events) == 1
        assert events[0]["eventId"] == CAMERA_EVENTS_RESPONSE[0]["eventId"]

        await mock_account.disconnect()

    async def test_device_id_property(
        self,
        mock_account: Account,
    ) -> None:
        """Test device_id property."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
        )
        assert client.device_id == CAMERA_DEVICE_ID

        await mock_account.disconnect()

    async def test_settings_headers_with_api_key(
        self,
        mock_account: Account,
    ) -> None:
        """Test that settings headers include x-api-key when provided."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="my-secret-key",
        )
        headers = client._settings_headers()
        assert headers["x-api-key"] == "my-secret-key"

        await mock_account.disconnect()

    async def test_settings_headers_without_api_key(
        self,
        mock_account: Account,
    ) -> None:
        """Test that settings headers are empty without api_key."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
        )
        headers = client._settings_headers()
        assert "x-api-key" not in headers

        await mock_account.disconnect()


class TestLitterRobot5Camera:
    """Tests for LitterRobot5 camera convenience methods."""

    async def test_has_camera_pro(
        self,
        mock_account: Account,
    ) -> None:
        """Test has_camera returns True for Pro model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        assert robot.has_camera is True

        await robot._account.disconnect()

    async def test_has_camera_standard(
        self,
        mock_account: Account,
    ) -> None:
        """Test has_camera returns False for standard model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
        assert robot.has_camera is False

        await robot._account.disconnect()

    async def test_camera_metadata_pro(
        self,
        mock_account: Account,
    ) -> None:
        """Test camera_metadata returns dict for Pro model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        assert robot.camera_metadata is not None
        assert robot.camera_metadata["deviceId"] == CAMERA_DEVICE_ID

        await robot._account.disconnect()

    async def test_get_camera_client(
        self,
        mock_account: Account,
    ) -> None:
        """Test get_camera_client returns a CameraClient."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()
        assert isinstance(client, CameraClient)
        assert client.device_id == CAMERA_DEVICE_ID

        await robot._account.disconnect()

    async def test_get_camera_session(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test get_camera_session returns a CameraSession."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        session = await robot.get_camera_session()
        assert isinstance(session, CameraSession)

        await robot._account.disconnect()

    async def test_get_camera_videos(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test get_camera_videos returns video clips."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        videos = await robot.get_camera_videos()
        assert len(videos) == 2
        assert isinstance(videos[0], VideoClip)

        await robot._account.disconnect()

    @staticmethod
    def _video_timezones(mock_aiointercept: aiointercept) -> list[str | None]:
        """Return the ``timezone`` sent with each clip-list request."""
        return [
            url.query.get("timezone")
            for (method, url) in mock_aiointercept.requests
            if method == "GET" and url.path.endswith("/videos")
        ]

    async def test_get_camera_videos_uses_robot_timezone(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Without a timezone, the robot's own timezone is sent."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        assert robot.timezone == "America/Denver"
        await robot.get_camera_videos()
        timezones = self._video_timezones(mock_aiointercept)
        assert timezones and set(timezones) == {"America/Denver"}

        await robot._account.disconnect()

    async def test_get_camera_videos_explicit_timezone_wins(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """An explicit timezone overrides the robot's."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        await robot.get_camera_videos(timezone="Australia/Sydney")
        timezones = self._video_timezones(mock_aiointercept)
        assert timezones and set(timezones) == {"Australia/Sydney"}

        await robot._account.disconnect()

    async def test_get_camera_videos_without_robot_timezone(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A robot with no timezone falls back to the system timezone."""
        monkeypatch.setenv("TZ", "America/Detroit")
        data = {**LITTER_ROBOT_5_PRO_DATA, "timezone": None}
        robot = LitterRobot5(data=data, account=mock_account)
        await robot.get_camera_videos()
        timezones = self._video_timezones(mock_aiointercept)
        assert timezones and set(timezones) == {"America/Detroit"}

        await robot._account.disconnect()

    async def test_set_camera_view_front(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test set_camera_view with 'front'."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        result = await robot.set_camera_view("front")
        assert result is True

        await robot._account.disconnect()

    async def test_set_camera_view_globe(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test set_camera_view with 'globe'."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        result = await robot.set_camera_view("globe")
        assert result is True

        await robot._account.disconnect()

    async def test_set_camera_view_invalid(
        self,
        mock_account: Account,
    ) -> None:
        """Test set_camera_view with invalid view name raises."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        with pytest.raises(InvalidCommandException, match="Invalid camera view"):
            await robot.set_camera_view("rear")

        await robot._account.disconnect()

    async def test_get_camera_view(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test get_camera_view maps the reported canvas to a view name."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        assert await robot.get_camera_view() == "front"

        await robot._account.disconnect()

    async def test_get_camera_view_unknown_canvas(
        self,
        mock_account: Account,
    ) -> None:
        """Test get_camera_view returns None for an unrecognized canvas."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        async def _canvas() -> str:
            return "sensor_9_4k"

        client.get_camera_canvas = _canvas  # type: ignore[method-assign]
        assert await robot.get_camera_view() is None

        await robot._account.disconnect()

    async def test_get_camera_status(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test get_camera_status on the robot."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        assert await robot.get_camera_status() == "ONLINE"

        await robot._account.disconnect()

    async def test_no_camera_raises(
        self,
        mock_account: Account,
    ) -> None:
        """Test get_camera_client raises for standard model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
        with pytest.raises(CameraNotAvailableException):
            robot.get_camera_client()

        await robot._account.disconnect()


class TestSignalingHelpers:
    """Tests for the module-level signaling parse helpers."""

    ANSWER_SDP = (
        "v=0\r\no=- 1 1 IN IP4 0.0.0.0\r\ns=-\r\nt=0 0\r\n"
        "m=video 9 UDP/TLS/RTP/SAVPF 96"
    )

    def test_parse_answer_base64(self) -> None:
        """Test parsing a base64-encoded SDP answer."""
        parsed = _parse_signaling_message(
            {"type": "answer", "sdp": encode(self.ANSWER_SDP)}
        )
        assert parsed == ("answer", self.ANSWER_SDP)

    def test_parse_answer_raw(self) -> None:
        """Test parsing a raw (non-base64) SDP answer."""
        parsed = _parse_signaling_message(
            {"type": "answer", "payload": self.ANSWER_SDP}
        )
        assert parsed == ("answer", self.ANSWER_SDP)

    def test_parse_answer_truncated(self) -> None:
        r"""Test that a truncated answer SDP is discarded.

        Observed live: the camera occasionally sends an answer payload that
        decodes to just ``"v=0\r\n"``, which the peer's SDP parser rejects
        ("Expect line: o=").
        """
        assert (
            _parse_signaling_message({"type": "answer", "payload": encode("v=0\r\n")})
            is None
        )
        assert _parse_signaling_message({"type": "answer", "payload": ""}) is None
        assert (
            _parse_signaling_message(
                {"type": "answer", "payload": "v=0\r\no=- 1 1 IN IP4 0.0.0.0"}
            )
            is None
        )

    def test_parse_candidate(self) -> None:
        """Test parsing an ICE candidate message."""
        parsed = _parse_signaling_message(
            {"candidate": "candidate:1 1 udp 2 1.2.3.4 5 typ host", "sdpMid": "1"}
        )
        assert parsed is not None
        kind, payload = parsed
        assert kind == "candidate"
        assert payload["sdpMid"] == "1"
        assert payload["sdpMLineIndex"] == 0

    def test_parse_candidate_null_fields(self) -> None:
        """Test explicit JSON nulls for sdpMid/sdpMLineIndex get defaults."""
        parsed = _parse_signaling_message(
            {
                "type": "candidate",
                "candidate": "candidate:1 1 udp 2 1.2.3.4 5 typ host",
                "sdpMid": None,
                "sdpMLineIndex": None,
            }
        )
        assert parsed is not None
        _, payload = parsed
        assert payload["sdpMid"] == "0"
        assert payload["sdpMLineIndex"] == 0

    def test_parse_empty_candidate(self) -> None:
        """Test that an empty candidate string is ignored."""
        assert _parse_signaling_message({"type": "candidate", "candidate": ""}) is None

    def test_parse_unknown_message(self) -> None:
        """Test that unknown message types are ignored."""
        assert _parse_signaling_message({"type": "status", "ok": True}) is None

    def test_decode_sdp_passthrough(self) -> None:
        """Test that non-base64 input is passed through unchanged."""
        assert _decode_sdp("not-base64!!") == "not-base64!!"
        assert _decode_sdp("v=0 raw sdp") == "v=0 raw sdp"

    def test_decode_sdp_base64_non_sdp(self) -> None:
        """Test that base64 input not decoding to SDP is passed through raw."""
        raw = encode("hello world")
        assert _decode_sdp(raw) == raw

    def test_parse_captured_answer(self) -> None:
        """Test an answer shaped like the live camera's (extra metadata keys)."""
        parsed = _parse_signaling_message(
            {
                "payload": encode(self.ANSWER_SDP),
                "type": "answer",
                "sessionId": "00000000-0000-4000-8000-000000000001",
                "originatior": "00000000-0000-4000-8000-000000000002",
            }
        )
        assert parsed == ("answer", self.ANSWER_SDP)

    def test_parse_captured_candidate(self) -> None:
        """Test a camera candidate without a ``type`` key, as sent live."""
        candidate = (
            "candidate:4048538384 1 udp 2122194687 192.168.1.10 50109 "
            "typ host generation 0 ufrag Y2Cx network-id 3 network-cost 10"
        )
        parsed = _parse_signaling_message(
            {
                "candidate": candidate,
                "sdpMLineIndex": 0,
                "sdpMid": "0",
                "sessionId": "00000000-0000-4000-8000-000000000001",
                "originatior": "00000000-0000-4000-8000-000000000002",
            }
        )
        assert parsed == (
            "candidate",
            {"candidate": candidate, "sdpMid": "0", "sdpMLineIndex": 0},
        )

    def test_session_is_expired(self) -> None:
        """Test CameraSession.is_expired against the session expiration."""
        now = utcnow()
        for expiration, expired in (
            (now - timedelta(seconds=1), True),
            (now + timedelta(seconds=60), False),
            (None, False),
        ):
            session = CameraSession(
                session_id="s",
                session_token="t",
                session_expiration=expiration,
                signaling_url="wss://host/sig",
            )
            assert session.is_expired is expired

    async def test_relay_reconnects_after_session_expiry(self) -> None:
        """Test late candidates are still forwarded past sessionExpiration.

        Observed live: the signaling server accepts an expired session token.
        """
        ws = _FakeWebSocket([])
        relay = CameraSignalingRelay(_fake_client([ws]))
        relay._session = CameraSession(
            session_id="s",
            session_token="t",
            session_expiration=utcnow() - timedelta(seconds=1),
            signaling_url="wss://host/sig",
        )
        relay._pending_candidates.append({"candidate": "candidate:1"})
        await relay._reconnect_and_flush()
        assert ws.sent == [{"candidate": "candidate:1"}]
        assert relay._pending_candidates == []

    def test_ws_url_encodes_token(self) -> None:
        """Test that the session token is URL-encoded in the ws URL."""
        session = CameraSession(
            session_id="s",
            session_token="ab+c/d=",
            session_expiration=None,
            signaling_url="wss://host/sig",
        )
        assert session.ws_url == "wss://host/sig?accessToken=ab%2Bc%2Fd%3D"

    async def test_finish_before_cancelling_outlasts_repeated_cancels(self) -> None:
        """Test repeated cancellations (e.g. overlapping stop()) still wait for the work."""
        release = asyncio.Event()
        task = asyncio.ensure_future(_finish_before_cancelling(release.wait()))
        try:
            await asyncio.sleep(0)
            for _ in range(2):  # the second one lands while already waiting
                task.cancel()
                for _ in range(3):
                    await asyncio.sleep(0)
            assert not task.done()

            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=1)
        finally:
            release.set()
            await _cancel_pending(task)


class _FakeWebSocket:
    """Signaling websocket stand-in that replays scripted camera messages."""

    def __init__(self, incoming: list[dict[str, Any]]) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        for msg in incoming:
            self._queue.put_nowait(msg)

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def ping(self) -> None:
        """Accept keepalive pings."""

    async def close(self) -> None:
        self.closed = True
        self._queue.put_nowait(None)

    def __aiter__(self) -> _FakeWebSocket:
        return self

    async def __anext__(self) -> Any:
        if (msg := await self._queue.get()) is None:
            raise StopAsyncIteration
        return SimpleNamespace(type=WSMsgType.TEXT, json=lambda: msg)


def _fake_client(sockets: list[_FakeWebSocket]) -> Any:
    """Return a CameraClient stand-in that hands out ``sockets`` in order."""
    remaining = list(sockets)
    sessions: list[CameraSession] = []

    async def generate_session() -> CameraSession:
        sessions.append(
            CameraSession(
                session_id=f"s{len(sessions)}",
                session_token="t",
                session_expiration=utcnow() + timedelta(seconds=60),
                signaling_url="wss://host/sig",
            )
        )
        return sessions[-1]

    async def ws_connect(*args: Any, **kwargs: Any) -> _FakeWebSocket:
        return remaining.pop(0)

    return SimpleNamespace(
        device_id=CAMERA_DEVICE_ID,
        generate_session=generate_session,
        websession=SimpleNamespace(ws_connect=ws_connect),
        sessions=sessions,
    )


async def _wait_for_event_or_task(
    event: asyncio.Event, task: asyncio.Future[Any], timeout: float = 1
) -> None:
    """Wait for ``event``; if ``task`` finishes first, surface its result."""
    waiter = asyncio.ensure_future(event.wait())
    try:
        await asyncio.wait(
            {waiter, task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
    if event.is_set():
        return
    if task.done():
        task.result()  # raises the startup error, if any
        pytest.fail("start() returned before reaching the awaited step")
    pytest.fail(f"neither the event nor the task finished within {timeout}s")


async def _wait_until(
    condition: Callable[[], object], task: asyncio.Future[Any], timeout: float = 1
) -> None:
    """Poll ``condition``; if ``task`` finishes first, surface its result."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if task.done():
            task.result()  # raises the startup error, if any
            pytest.fail("start() returned before reaching the awaited step")
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail(f"condition not met within {timeout}s")
        await asyncio.sleep(0)


async def _cancel_pending(task: asyncio.Future[Any]) -> None:
    """Cancel ``task`` if still running and wait for it to finish."""
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def _deadline_with(on_deadline: Any) -> Any:
    """Return an ``asyncio.timeout`` stand-in that fires as an answer lands.

    Entering schedules ``on_deadline`` (the answer arriving) and then the
    timeout's cancellation in the same loop iteration, as a real deadline
    racing a real answer would.
    """

    class _Deadline:
        def __init__(self, delay: float) -> None:
            self._task: asyncio.Task[Any] | None = None

        async def __aenter__(self) -> _Deadline:
            self._task = task = asyncio.current_task()
            assert task is not None

            def fire() -> None:
                on_deadline()
                task.cancel()

            asyncio.get_running_loop().call_soon(fire)
            return self

        async def __aexit__(self, exc_type: Any, *exc: Any) -> bool:
            if exc_type is asyncio.CancelledError:
                assert self._task is not None
                self._task.uncancel()
                raise TimeoutError
            return False

    return _Deadline


def cast_session(session: Any) -> CameraSession:
    """Narrow a fake client's session for mypy."""
    assert isinstance(session, CameraSession)
    return session


class TestAnswerTimeout:
    """Tests for retrying an offer the camera never answers."""

    ANSWER_SDP = TestSignalingHelpers.ANSWER_SDP
    ANSWER = {"type": "answer", "payload": encode(ANSWER_SDP)}
    CANDIDATE = {"candidate": "candidate:1 1 udp 2 1.2.3.4 5 typ host"}

    @pytest.fixture(autouse=True)
    def _short_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(camera, "ANSWER_TIMEOUT", 0.05)

    async def test_relay_answer_first_attempt(self) -> None:
        """Test the relay returns once the camera answers."""
        ws = _FakeWebSocket([self.ANSWER, self.CANDIDATE])
        client = _fake_client([ws])
        answers: list[str] = []
        candidates: list[dict[str, Any]] = []
        relay = CameraSignalingRelay(client)

        session = await relay.start("v=0 offer", answers.append, candidates.append)
        await asyncio.sleep(0)

        assert session is client.sessions[0]
        assert answers == [self.ANSWER_SDP]
        assert candidates[0]["candidate"] == self.CANDIDATE["candidate"]
        assert ws.sent[0] == {"type": "offer", "sdp": encode("v=0 offer")}
        await relay.close()
        assert ws.closed

    async def test_relay_retries_on_fresh_session(self) -> None:
        """Test an unanswered offer is resent, with early candidates, on a new session."""
        silent, answering = _FakeWebSocket([]), _FakeWebSocket([self.ANSWER])
        client = _fake_client([silent, answering])
        answers: list[str] = []
        relay = CameraSignalingRelay(client)
        browser_candidate = {"candidate": "candidate:9", "sdpMid": "0"}
        await relay.send_candidate(browser_candidate)

        session = await relay.start("v=0 offer", answers.append, lambda c: None)

        assert len(client.sessions) == 2
        assert session is client.sessions[1]
        assert silent.closed
        assert answers == [self.ANSWER_SDP]
        offer, candidate = answering.sent
        assert offer["type"] == "offer"
        assert candidate["candidate"] == "candidate:9"
        await relay.close()

    async def test_relay_closes_socket_when_cancelled_during_offer(self) -> None:
        """Test cancelling start() while the offer is sent closes the socket."""
        sending = asyncio.Event()

        class _StalledWebSocket(_FakeWebSocket):
            async def send_json(self, data: dict[str, Any]) -> None:
                sending.set()
                await asyncio.Event().wait()  # never completes

        ws = _StalledWebSocket([])
        relay = CameraSignalingRelay(_fake_client([ws]))
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        try:
            await _wait_for_event_or_task(sending, task)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task
            assert ws.closed
            assert relay.session is None
        finally:
            await _cancel_pending(task)

    @pytest.mark.parametrize("stall_offer", [True, False])
    async def test_relay_cancel_bounded_when_close_hangs(
        self, monkeypatch: pytest.MonkeyPatch, stall_offer: bool
    ) -> None:
        """Test cancelling start() is not held up by a socket close that hangs.

        Covers cancellation while sending the offer and while waiting for
        the answer; either way the original CancelledError propagates.
        """
        monkeypatch.setattr(camera, "WS_CLOSE_TIMEOUT", 0.05)
        monkeypatch.setattr(camera, "ANSWER_TIMEOUT", 60)
        offered = asyncio.Event()

        class _HangingCloseWebSocket(_FakeWebSocket):
            close_called = False

            async def send_json(self, data: dict[str, Any]) -> None:
                offered.set()
                if stall_offer:
                    await asyncio.Event().wait()

            async def close(self) -> None:
                self.close_called = True
                await asyncio.Event().wait()  # server never answers the close

        ws = _HangingCloseWebSocket([])
        relay = CameraSignalingRelay(_fake_client([ws]))
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        try:
            await _wait_for_event_or_task(offered, task)
            await asyncio.sleep(0)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=1)
            assert ws.close_called
            assert relay.session is None
        finally:
            await _cancel_pending(task)

    @staticmethod
    def _recording_relay() -> tuple[CameraSignalingRelay, list[tuple[Any, Any]]]:
        """Return a relay whose attempts only record their callbacks."""
        relay = CameraSignalingRelay(_fake_client([]))
        handlers: list[tuple[Any, Any]] = []

        async def connect_and_offer(
            offer_sdp: str, on_answer: Any, on_candidate: Any
        ) -> CameraSession:
            handlers.append((on_answer, on_candidate))
            return CameraSession(
                session_id=f"s{len(handlers)}",
                session_token="t",
                session_expiration=None,
                signaling_url="wss://host/sig",
            )

        relay._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        return relay, handlers

    async def test_relay_ignores_abandoned_attempt(self) -> None:
        """Test a timed-out attempt's late answer and candidates are dropped."""
        relay, handlers = self._recording_relay()
        answers: list[str] = []
        candidates: list[dict[str, Any]] = []
        task = asyncio.ensure_future(
            relay.start("v=0 offer", answers.append, candidates.append)
        )
        try:
            await _wait_until(lambda: len(handlers) >= 2, task)

            stale_answer, stale_candidate = handlers[0]
            stale_answer("v=0 stale")
            stale_candidate({"candidate": "candidate:stale"})
            await asyncio.sleep(0)
            assert answers == []
            assert candidates == []
            assert not task.done()  # the retry still waits for its own answer

            handlers[1][0]("v=0 fresh")
            session = await task
            assert session.session_id == "s2"
            assert answers == ["v=0 fresh"]
        finally:
            await _cancel_pending(task)

    async def test_relay_accepts_answer_at_deadline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test an answer that lands as the timeout fires is not retried."""
        relay, handlers = self._recording_relay()
        answers: list[str] = []
        monkeypatch.setattr(
            asyncio,
            "timeout",
            _deadline_with(lambda: handlers[-1][0]("v=0 at deadline")),
        )

        session = await relay.start("v=0 offer", answers.append, lambda c: None)

        assert len(handlers) == 1
        assert session.session_id == "s1"
        assert answers == ["v=0 at deadline"]

    async def test_stream_accepts_answer_at_deadline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test CameraStream keeps a peer whose answer lands at the deadline."""
        if not camera.HAS_AIORTC:
            pytest.skip("aiortc not installed")
        stream = CameraStream(_fake_client([]))
        attempts = 0

        async def connect_and_offer() -> None:
            nonlocal attempts
            attempts += 1

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        # start() replaces _answered per attempt, so look it up when firing
        monkeypatch.setattr(
            asyncio, "timeout", _deadline_with(lambda: stream._answered.set())
        )
        await stream.start()

        assert attempts == 1
        await stream.stop()

    async def test_relay_flushes_failed_send_once_answered(self) -> None:
        """Test a candidate whose send failed before the answer is still delivered.

        The server closes the socket right after the answer, so a send can
        fail while the answer is already on its way.
        """

        class _ClosingWebSocket(_FakeWebSocket):
            async def send_json(self, data: dict[str, Any]) -> None:
                if data.get("type") == "candidate":
                    raise ConnectionResetError("closing transport")
                await super().send_json(data)

        ws, reconnect = _ClosingWebSocket([]), _FakeWebSocket([])
        relay = CameraSignalingRelay(_fake_client([ws, reconnect]))
        answers: list[str] = []
        task = asyncio.ensure_future(
            relay.start("v=0 offer", answers.append, lambda c: None)
        )
        try:
            await _wait_until(lambda: ws.sent, task)  # the offer was sent
            await relay.send_candidate({"candidate": "candidate:late"})
            ws._queue.put_nowait(self.ANSWER)
            await asyncio.wait_for(task, timeout=1)
            await asyncio.wait_for(relay._reconnect_task, timeout=1)  # type: ignore[arg-type]
        finally:
            await _cancel_pending(task)

        assert answers == [self.ANSWER_SDP]
        assert reconnect.sent[0]["candidate"] == "candidate:late"
        await relay.close()

    async def test_relay_close_during_setup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test close() while the session is being created leaves no socket open."""
        # a long answer wait, so only an immediate closed check can pass
        monkeypatch.setattr(camera, "ANSWER_TIMEOUT", 60)
        ws = _FakeWebSocket([])
        client = _fake_client([ws])
        release = asyncio.Event()
        generate_session = client.generate_session

        async def slow_generate_session() -> CameraSession:
            await release.wait()
            return cast_session(await generate_session())

        client.generate_session = slow_generate_session
        handed_out: list[_FakeWebSocket] = []
        ws_connect = client.websession.ws_connect

        async def recording_ws_connect(*args: Any, **kwargs: Any) -> _FakeWebSocket:
            handed_out.append(await ws_connect(*args, **kwargs))
            return handed_out[-1]

        client.websession = SimpleNamespace(ws_connect=recording_ws_connect)
        relay = CameraSignalingRelay(client)
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        try:
            await asyncio.sleep(0)
            await relay.close()
            release.set()

            with pytest.raises(CameraStreamException, match="closed"):
                await asyncio.wait_for(task, timeout=1)
        finally:
            await _cancel_pending(task)
        # never opening a socket is fine; one that was opened must be closed
        assert all(sock.closed for sock in handed_out)

    async def test_relay_second_start_rejected_during_setup(self) -> None:
        """Test a second start() is rejected while the first creates its session."""
        client = _fake_client([_FakeWebSocket([])])
        release = asyncio.Event()

        async def slow_generate_session() -> CameraSession:
            await release.wait()
            raise CameraStreamException("session failed")

        client.generate_session = slow_generate_session
        relay = CameraSignalingRelay(client)
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        try:
            await asyncio.sleep(0)
            with pytest.raises(CameraStreamException, match="already started"):
                # a regressed guard would block on the session; fail promptly
                async with asyncio.timeout(1):
                    await relay.start("v=0 other", lambda a: None, lambda c: None)

            release.set()
            with pytest.raises(CameraStreamException, match="session failed"):
                await asyncio.wait_for(task, timeout=1)
        finally:
            await _cancel_pending(task)
        # the first start() failed during setup, so the guard is released
        assert not relay._starting

    async def test_relay_resets_answered_state_when_start_aborted(self) -> None:
        """Test start() cancelled after the answer leaves no 'answered' state."""
        relay, handlers = self._recording_relay()
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        try:
            await _wait_until(lambda: handlers, task)
            handlers[0][0]("v=0 answer")
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await _cancel_pending(task)

        assert relay._started is False
        await relay.send_candidate({"candidate": "candidate:next-offer"})
        assert relay._offer_candidates[-1]["candidate"] == "candidate:next-offer"
        assert relay._pending_candidates == []

    async def test_relay_recovers_when_early_candidate_send_fails(self) -> None:
        """Test a failed early-candidate send keeps the answer and flushes later."""

        class _ClosingWebSocket(_FakeWebSocket):
            async def send_json(self, data: dict[str, Any]) -> None:
                if data.get("type") == "candidate":
                    raise ConnectionResetError("closing transport")
                await super().send_json(data)

        ws = _ClosingWebSocket([self.ANSWER])
        reconnect = _FakeWebSocket([])
        relay = CameraSignalingRelay(_fake_client([ws, reconnect]))
        await relay.send_candidate({"candidate": "candidate:early"})
        answers: list[str] = []

        session = await asyncio.wait_for(
            relay.start("v=0 offer", answers.append, lambda c: None), timeout=1
        )
        await asyncio.wait_for(relay._reconnect_task, timeout=1)  # type: ignore[arg-type]

        assert session.session_id == "s0"
        assert answers == [self.ANSWER_SDP]
        assert reconnect.sent[0]["candidate"] == "candidate:early"
        await relay.close()

    @staticmethod
    def _stalled_setup_socket() -> Any:
        """Return a socket whose offer write stalls and whose close blocks.

        ``sending`` is set when the offer write starts, ``closing`` when its
        close starts; the close completes once ``release`` is set.
        """

        class _StalledWebSocket(_FakeWebSocket):
            sending = asyncio.Event()
            closing = asyncio.Event()
            release = asyncio.Event()

            async def send_json(self, data: dict[str, Any]) -> None:
                self.sending.set()
                await asyncio.Event().wait()  # never completes

            async def close(self) -> None:
                self.closing.set()
                await self.release.wait()
                await super().close()

        return _StalledWebSocket([])

    async def test_relay_close_cancels_offer_setup(self) -> None:
        """Test close() during the offer write waits for that socket's cleanup."""
        ws = self._stalled_setup_socket()
        relay = CameraSignalingRelay(_fake_client([ws]))
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        close: asyncio.Future[None] | None = None
        try:
            await _wait_for_event_or_task(ws.sending, task)
            close = asyncio.ensure_future(relay.close())
            await _wait_for_event_or_task(ws.closing, close)
            await asyncio.sleep(0)
            assert not close.done()  # still waiting for the socket cleanup

            ws.release.set()
            await asyncio.wait_for(close, timeout=1)
            assert ws.closed
            with pytest.raises(CameraStreamException, match="closed"):
                await asyncio.wait_for(task, timeout=1)
        finally:
            if close is not None:
                await _cancel_pending(close)
            await _cancel_pending(task)

    async def test_relay_close_cancelled_still_finishes_setup_cleanup(self) -> None:
        """Test cancelling close() propagates, without abandoning setup cleanup."""
        ws = self._stalled_setup_socket()
        relay = CameraSignalingRelay(_fake_client([ws]))
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        close: asyncio.Future[None] | None = None
        try:
            await _wait_for_event_or_task(ws.sending, task)
            close = asyncio.ensure_future(relay.close())
            await _wait_for_event_or_task(ws.closing, close)
            close.cancel()
            with pytest.raises(asyncio.CancelledError):
                await close  # not swallowed

            ws.release.set()
            with pytest.raises(CameraStreamException, match="closed"):
                await asyncio.wait_for(task, timeout=1)
            assert ws.closed  # the setup's cleanup still ran to completion
        finally:
            if close is not None:
                await _cancel_pending(close)
            await _cancel_pending(task)

    async def test_relay_close_wakes_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test close() ends a start() that is waiting for the answer."""
        monkeypatch.setattr(camera, "ANSWER_TIMEOUT", 60)
        relay, handlers = self._recording_relay()
        task = asyncio.ensure_future(
            relay.start("v=0 offer", lambda a: None, lambda c: None)
        )
        try:
            await _wait_until(lambda: handlers, task)
            await relay.close()
            with pytest.raises(CameraStreamException, match="closed"):
                await asyncio.wait_for(task, timeout=1)
        finally:
            await _cancel_pending(task)

    async def test_relay_raises_when_never_answered(self) -> None:
        """Test the relay gives up after ANSWER_ATTEMPTS unanswered offers."""
        sockets = [_FakeWebSocket([]), _FakeWebSocket([])]
        relay = CameraSignalingRelay(_fake_client(sockets))
        await relay.send_candidate({"candidate": "candidate:old-offer"})

        with pytest.raises(CameraStreamException, match="did not answer"):
            await relay.start("v=0 offer", lambda a: None, lambda c: None)

        assert all(ws.closed for ws in sockets)
        assert relay.session is None
        # both attempts replayed it; a new offer must not
        assert all(ws.sent[1]["candidate"] == "candidate:old-offer" for ws in sockets)
        assert relay._offer_candidates == []

    async def test_stream_retries_then_raises(self) -> None:
        """Test CameraStream retries an unanswered offer, then raises."""
        if not camera.HAS_AIORTC:
            pytest.skip("aiortc not installed")
        stream = CameraStream(_fake_client([]))
        closed: list[Any] = []
        attempts = 0

        async def connect_and_offer() -> None:
            nonlocal attempts
            attempts += 1
            stream._ws = _FakeWebSocket([])
            closed.append(stream._ws)

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        with pytest.raises(CameraStreamException, match="did not answer"):
            await stream.start()

        assert attempts == 2
        assert all(ws.closed for ws in closed)

    async def test_stream_answer_on_retry(self) -> None:
        """Test CameraStream returns once a retried offer is answered."""
        if not camera.HAS_AIORTC:
            pytest.skip("aiortc not installed")
        stream = CameraStream(_fake_client([]))
        attempts = 0

        async def connect_and_offer() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                stream._answered.set()

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        await stream.start()

        assert attempts == 2
        await stream.stop()

    async def test_relay_start_again_after_never_answered(self) -> None:
        """Test start() can be called again after the camera never answered."""
        sockets = [_FakeWebSocket([]), _FakeWebSocket([])]
        answering = _FakeWebSocket([self.ANSWER])
        client = _fake_client([*sockets, answering])
        answers: list[str] = []
        relay = CameraSignalingRelay(client)

        with pytest.raises(CameraStreamException, match="did not answer"):
            await relay.start("v=0 offer", answers.append, lambda c: None)
        session = await relay.start("v=0 offer", answers.append, lambda c: None)

        assert session is client.sessions[2]
        assert answers == [self.ANSWER_SDP]
        await relay.close()

    async def test_stream_start_again_after_never_answered(self) -> None:
        """Test CameraStream.start() can be called again after it raised."""
        if not camera.HAS_AIORTC:
            pytest.skip("aiortc not installed")
        stream = CameraStream(_fake_client([]))
        attempts = 0

        async def connect_and_offer() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 3:
                stream._answered.set()

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        with pytest.raises(CameraStreamException, match="did not answer"):
            await stream.start()
        await stream.start()

        assert attempts == 3
        await stream.stop()


class TestRelayReconnect:
    """Tests for delivering late ICE candidates over a fresh connection."""

    @pytest.fixture(autouse=True)
    def _fast_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(camera, "RECONNECT_BACKOFF", 0.01)

    @staticmethod
    def _relay(ws_connect: Any) -> CameraSignalingRelay:
        client = _fake_client([])
        client.websession = SimpleNamespace(ws_connect=ws_connect)
        relay = CameraSignalingRelay(client)
        relay._session = CameraSession(
            session_id="s",
            session_token="t",
            session_expiration=None,
            signaling_url="wss://host/sig",
        )
        return relay

    async def test_retries_failed_handshake(self) -> None:
        """Test a transient reconnect failure is retried."""
        ws = _FakeWebSocket([])
        attempts = 0

        async def flaky_ws_connect(*args: Any, **kwargs: Any) -> _FakeWebSocket:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("handshake failed")
            return ws

        relay = self._relay(flaky_ws_connect)
        relay._pending_candidates.append({"candidate": "candidate:late"})
        await asyncio.wait_for(relay._reconnect_and_flush(), timeout=1)

        assert attempts == 2
        assert ws.sent == [{"candidate": "candidate:late"}]
        assert relay._pending_candidates == []

    async def test_retries_only_unsent_after_partial_flush(self) -> None:
        """Test a flush that fails partway resends only the unsent candidates."""

        class _FailsSecondSend(_FakeWebSocket):
            async def send_json(self, data: dict[str, Any]) -> None:
                if self.sent:
                    raise ConnectionResetError("closing transport")
                await super().send_json(data)

        sockets: list[_FakeWebSocket] = [_FailsSecondSend([]), _FakeWebSocket([])]

        async def ws_connect(*args: Any, **kwargs: Any) -> _FakeWebSocket:
            return sockets.pop(0)

        first, second = sockets
        relay = self._relay(ws_connect)
        relay._pending_candidates.extend(
            [{"candidate": "candidate:a"}, {"candidate": "candidate:b"}]
        )
        await asyncio.wait_for(relay._reconnect_and_flush(), timeout=1)

        assert first.sent == [{"candidate": "candidate:a"}]
        assert second.sent == [{"candidate": "candidate:b"}]
        assert first.closed and second.closed

    async def test_restored_batch_stays_bounded(self) -> None:
        """Test a failed batch plus new arrivals keeps only the newest candidates."""
        limit = camera.MAX_PENDING_CANDIDATES
        relay: CameraSignalingRelay

        class _ArrivalsThenFail(_FakeWebSocket):
            async def send_json(self, data: dict[str, Any]) -> None:
                # browser candidates arrive while this send is in flight
                for i in range(limit):
                    relay._pending_candidates.append({"candidate": f"new{i}"})
                raise ConnectionResetError("closing transport")

        sockets: list[_FakeWebSocket] = [_ArrivalsThenFail([])]

        async def ws_connect(*args: Any, **kwargs: Any) -> _FakeWebSocket:
            if not sockets:
                raise ConnectionError("handshake failed")
            return sockets.pop(0)

        relay = self._relay(ws_connect)
        relay._pending_candidates.extend({"candidate": f"old{i}"} for i in range(limit))
        await asyncio.wait_for(relay._reconnect_and_flush(), timeout=1)

        queued = [c["candidate"] for c in relay._pending_candidates]
        assert len(queued) == limit
        assert queued == [f"new{i}" for i in range(limit)]  # newest, in order

    async def test_gives_up_after_max_attempts(self) -> None:
        """Test the flush stops after RECONNECT_ATTEMPTS, keeping the candidates."""
        attempts = 0

        async def failing_ws_connect(*args: Any, **kwargs: Any) -> Any:
            nonlocal attempts
            attempts += 1
            raise ConnectionError("handshake failed")

        relay = self._relay(failing_ws_connect)
        relay._pending_candidates.append({"candidate": "candidate:late"})
        await asyncio.wait_for(relay._reconnect_and_flush(), timeout=1)

        assert attempts == camera.RECONNECT_ATTEMPTS
        assert relay._pending_candidates == [{"candidate": "candidate:late"}]

    async def test_bounded_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test a reconnect socket whose close hangs does not stall the flush."""
        monkeypatch.setattr(camera, "WS_CLOSE_TIMEOUT", 0.05)

        class _HangingCloseWebSocket(_FakeWebSocket):
            async def close(self) -> None:
                await asyncio.Event().wait()

        ws = _HangingCloseWebSocket([])

        async def ws_connect(*args: Any, **kwargs: Any) -> _FakeWebSocket:
            return ws

        relay = self._relay(ws_connect)
        relay._pending_candidates.append({"candidate": "candidate:late"})
        await asyncio.wait_for(relay._reconnect_and_flush(), timeout=1)
        assert ws.sent == [{"candidate": "candidate:late"}]


class TestCameraStreamLifecycle:
    """Tests for CameraStream start/stop edge cases."""

    @pytest.fixture(autouse=True)
    def _require_aiortc(self) -> None:
        if not camera.HAS_AIORTC:
            pytest.skip("aiortc not installed")

    async def test_second_start_rejected_during_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test the start() guard holds between retry attempts."""
        monkeypatch.setattr(camera, "ANSWER_TIMEOUT", 0.05)
        stream = CameraStream(_fake_client([]))
        retrying = asyncio.Event()
        attempts = 0

        async def connect_and_offer() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                retrying.set()
                await asyncio.Event().wait()

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        task = asyncio.ensure_future(stream.start())
        try:
            await _wait_for_event_or_task(retrying, task)
            assert stream._pc is None  # the old guard alone would pass here
            with pytest.raises(CameraStreamException, match="already started"):
                await stream.start()
        finally:
            await _cancel_pending(task)
        await stream.stop()

    @staticmethod
    def _local_stream(
        monkeypatch: pytest.MonkeyPatch, sockets: list[_FakeWebSocket]
    ) -> tuple[CameraStream, Any]:
        """Return a stream that negotiates with host candidates only (no STUN)."""
        monkeypatch.setattr(
            CameraStream, "_build_ice_servers", staticmethod(lambda creds: [])
        )
        client = _fake_client(sockets)
        return CameraStream(client), client

    async def test_detached_peer_events_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test a peer detached by teardown can't add tracks or signal readiness.

        aiortc drops listeners when the peer closes, so the late events are
        fired mid-teardown, while the signaling socket is being closed.
        """
        peers: list[Any] = []

        def report(pc: Any) -> None:
            pc.emit("track", SimpleNamespace(kind="video", id=f"t{id(pc)}"))
            setattr(pc, "_RTCPeerConnection__connectionState", "connected")
            pc.emit("connectionstatechange")

        class _EventsDuringCloseWebSocket(_FakeWebSocket):
            async def close(self) -> None:
                report(peers[0])  # the peer finishes connecting during teardown
                await asyncio.sleep(0)
                await super().close()

        stream, _ = self._local_stream(monkeypatch, [_EventsDuringCloseWebSocket([])])
        states: list[str] = []
        stream.on_connection_state_change(states.append)
        await stream._connect_and_offer()
        peers.append(stream._pc)

        # the current peer's events are handled
        report(peers[0])
        await asyncio.sleep(0)
        assert "video" in stream._tracks
        assert stream._connected.is_set()
        assert states == ["connected"]
        stream._tracks.clear()
        stream._connected.clear()
        states.clear()

        await stream._disconnect()  # a retry's teardown
        await asyncio.sleep(0)

        assert stream._tracks == {}
        assert not stream._connected.is_set()
        assert states == []
        await stream.stop()

    async def test_stop_during_ice_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test stop() mid-setup ends start() with a stopped error, nothing left open."""
        ws = _FakeWebSocket([])
        stream, client = self._local_stream(monkeypatch, [ws])
        ws_connect = client.websession.ws_connect

        async def ws_connect_then_stop(*args: Any, **kwargs: Any) -> Any:
            # stop() runs at setup's next await (offer creation / ICE gathering)
            asyncio.ensure_future(stream.stop())
            return await ws_connect(*args, **kwargs)

        client.websession = SimpleNamespace(ws_connect=ws_connect_then_stop)
        with pytest.raises(CameraStreamException, match="stopped"):
            await asyncio.wait_for(stream.start(), timeout=5)
        assert ws.closed
        assert stream._pc is None
        assert stream._ws is None

    async def test_stop_during_turn_allocation_closes_socket(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test stop() during a TURN allocation leaves no relay socket open.

        aioice runs the allocation in its own task, so interrupting gathering
        orphaned it: when the server then answered, the relay socket stayed
        open (and kept refreshing) until the event loop closed.
        """
        # pylint: disable=import-outside-toplevel
        from aioice import stun
        from aioice.turn import make_integrity_key
        from aiortc import RTCIceServer

        loop = asyncio.get_running_loop()
        requested, release = asyncio.Event(), asyncio.Event()
        realm, nonce = "test", b"nonce"
        key = make_integrity_key("u", realm, "p")

        class _TurnServer(asyncio.DatagramProtocol):
            """Grants allocations once ``release`` is set."""

            transport: asyncio.DatagramTransport

            def connection_made(self, transport: Any) -> None:
                self.transport = transport

            def datagram_received(self, data: bytes, addr: Any) -> None:
                request = stun.parse_message(data)
                tid = request.transaction_id
                if "MESSAGE-INTEGRITY" not in request.attributes:
                    response = stun.Message(
                        request.message_method, stun.Class.ERROR, tid
                    )
                    response.attributes["ERROR-CODE"] = (401, "Unauthorized")
                    response.attributes["REALM"] = realm
                    response.attributes["NONCE"] = nonce
                    self.transport.sendto(bytes(response), addr)
                    return
                response = stun.Message(
                    request.message_method, stun.Class.RESPONSE, tid
                )
                response.attributes["LIFETIME"] = request.attributes["LIFETIME"]
                if request.message_method == stun.Method.ALLOCATE:
                    response.attributes["XOR-MAPPED-ADDRESS"] = addr
                    response.attributes["XOR-RELAYED-ADDRESS"] = ("127.0.0.1", 9)
                response.add_message_integrity(key)
                if request.message_method != stun.Method.ALLOCATE:
                    self.transport.sendto(bytes(response), addr)
                    return
                requested.set()

                async def grant() -> None:
                    await release.wait()
                    self.transport.sendto(bytes(response), addr)

                grants.append(asyncio.ensure_future(grant()))

        grants: list[asyncio.Future[None]] = []
        server, _ = await loop.create_datagram_endpoint(
            _TurnServer, local_addr=("127.0.0.1", 0)
        )
        server_addr = server.get_extra_info("sockname")
        relay_sockets: list[asyncio.BaseTransport] = []
        create_datagram_endpoint = loop.create_datagram_endpoint

        async def tracking_endpoint(*args: Any, **kwargs: Any) -> Any:
            transport, protocol = await create_datagram_endpoint(*args, **kwargs)
            if kwargs.get("remote_addr") == server_addr:
                relay_sockets.append(transport)
            return transport, protocol

        monkeypatch.setattr(loop, "create_datagram_endpoint", tracking_endpoint)
        stream, _ = self._local_stream(monkeypatch, [_FakeWebSocket([])])
        turn = RTCIceServer(
            urls=f"turn:{server_addr[0]}:{server_addr[1]}",
            username="u",
            credential="p",
        )
        monkeypatch.setattr(
            CameraStream, "_build_ice_servers", staticmethod(lambda creds: [turn])
        )
        task = asyncio.ensure_future(stream.start())
        stop: asyncio.Future[None] | None = None
        try:
            await _wait_for_event_or_task(requested, task, timeout=5)
            assert requested.is_set()
            stop = asyncio.ensure_future(stream.stop())
            await asyncio.sleep(0.05)
            release.set()  # the allocation succeeds after stop() was called
            await asyncio.wait_for(stop, timeout=5)
            with pytest.raises(CameraStreamException, match="stopped"):
                await asyncio.wait_for(task, timeout=1)
            await asyncio.sleep(0.1)  # time for an orphaned allocation to finish
        finally:
            await _cancel_pending(task)
            if stop is not None:
                await _cancel_pending(stop)
            for grant in grants:
                await _cancel_pending(grant)
            server.close()
        assert relay_sockets
        assert all(sock.is_closing() for sock in relay_sockets)

    async def test_stop_cancels_in_flight_connect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test stop() during the signaling handshake ends setup before returning."""
        stream, client = self._local_stream(monkeypatch, [])
        connecting = asyncio.Event()
        opened: list[Any] = []

        async def slow_ws_connect(*args: Any, **kwargs: Any) -> Any:
            connecting.set()
            await asyncio.Event().wait()  # the handshake never completes
            opened.append(object())

        client.websession = SimpleNamespace(ws_connect=slow_ws_connect)
        task = asyncio.ensure_future(stream.start())
        try:
            await _wait_for_event_or_task(connecting, task)
            await asyncio.wait_for(stream.stop(), timeout=1)
            assert stream._setup_task is None
            with pytest.raises(CameraStreamException, match="stopped"):
                await asyncio.wait_for(task, timeout=1)
        finally:
            await _cancel_pending(task)
        assert opened == []
        assert stream._pc is None

    async def test_cancelled_stop_cannot_interrupt_peer_close(self) -> None:
        """Test a cancelled stop() leaves the peer close running; stop() again joins it."""
        closing, release = asyncio.Event(), asyncio.Event()
        closes = 0

        class _SlowPeer:
            async def close(self) -> None:
                nonlocal closes
                closes += 1
                closing.set()
                await release.wait()

        stream = CameraStream(_fake_client([]))
        stream._pc = _SlowPeer()
        first = asyncio.ensure_future(stream.stop())
        second: asyncio.Future[None] | None = None
        try:
            await _wait_for_event_or_task(closing, first)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first

            second = asyncio.ensure_future(stream.stop())
            await asyncio.sleep(0)
            assert not second.done()  # waits for the same peer close

            release.set()
            await asyncio.wait_for(second, timeout=1)
        finally:
            await _cancel_pending(first)
            if second is not None:
                await _cancel_pending(second)
        assert closes == 1
        assert stream._teardown_task is not None and stream._teardown_task.done()

    async def test_stop_wakes_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test stop() ends a start() that is waiting for the answer."""
        monkeypatch.setattr(camera, "ANSWER_TIMEOUT", 60)
        stream = CameraStream(_fake_client([]))
        offered = asyncio.Event()

        async def connect_and_offer() -> None:
            offered.set()

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        task = asyncio.ensure_future(stream.start())
        try:
            await _wait_for_event_or_task(offered, task)
            await asyncio.sleep(0)
            await stream.stop()
            with pytest.raises(CameraStreamException, match="stopped"):
                await asyncio.wait_for(task, timeout=1)
        finally:
            await _cancel_pending(task)

    async def test_stop_during_setup(self) -> None:
        """Test stop() while the session is being set up leaves no socket open."""
        stream = CameraStream(_fake_client([]))
        ws = _FakeWebSocket([])

        async def connect_and_offer() -> None:
            stream._stopped = True  # stop() ran while this was in progress
            stream._ws = ws

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        with pytest.raises(CameraStreamException, match="stopped"):
            await asyncio.wait_for(stream.start(), timeout=1)
        assert ws.closed
        assert stream._ws is None

    async def test_cancelled_teardown_still_closes_peer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test a cancellation during teardown still closes the detached peer."""
        monkeypatch.setattr(camera, "WS_CLOSE_TIMEOUT", 0.05)
        closing = asyncio.Event()

        class _HangingCloseWebSocket(_FakeWebSocket):
            async def close(self) -> None:
                closing.set()
                await asyncio.Event().wait()

        peer_closed = asyncio.Event()

        class _Peer:
            async def close(self) -> None:
                peer_closed.set()

        stream = CameraStream(_fake_client([]))
        stream._pc = _Peer()
        stream._ws = _HangingCloseWebSocket([])
        task = asyncio.ensure_future(stream.stop())
        try:
            await _wait_for_event_or_task(closing, task)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await _cancel_pending(task)
        # the teardown carries on past the socket close timeout
        await asyncio.wait_for(peer_closed.wait(), timeout=1)
        assert stream._pc is None

    async def test_stop_waits_for_overlapping_teardown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test stop() during a retry's teardown returns only once the peer is closed.

        The retry has already detached the peer and the socket reports closed
        while its close handshake runs, so stop() finds nothing of its own.
        """
        monkeypatch.setattr(camera, "WS_CLOSE_TIMEOUT", 60)
        closing, release = asyncio.Event(), asyncio.Event()

        class _SlowCloseWebSocket(_FakeWebSocket):
            async def close(self) -> None:
                self.closed = True  # aiohttp marks it closed before the handshake
                closing.set()
                await release.wait()

        peer_closed = asyncio.Event()

        class _Peer:
            async def close(self) -> None:
                peer_closed.set()

        stream = CameraStream(_fake_client([]))
        stream._pc = _Peer()
        stream._ws = _SlowCloseWebSocket([])
        retry = asyncio.ensure_future(stream._disconnect())
        stop: asyncio.Future[None] | None = None
        try:
            await _wait_for_event_or_task(closing, retry)
            stop = asyncio.ensure_future(stream.stop())
            for _ in range(5):
                await asyncio.sleep(0)
            assert not stop.done()  # waits for the retry's teardown

            release.set()
            await asyncio.wait_for(stop, timeout=1)
            assert peer_closed.is_set()
            await asyncio.wait_for(retry, timeout=1)
        finally:
            release.set()  # unblock the owned teardown if an assertion failed
            await _cancel_pending(retry)
            if stop is not None:
                await _cancel_pending(stop)
            if stream._teardown_task is not None:
                await asyncio.wait({stream._teardown_task}, timeout=1)
        assert stream._pc is None

    async def test_start_waits_for_pending_teardown(self) -> None:
        """Test start() waits for a teardown left running by a cancelled start().

        Otherwise the old teardown would clear the new attempt's socket.
        """
        stream = CameraStream(_fake_client([]))
        release = asyncio.Event()
        stream._teardown_task = asyncio.ensure_future(release.wait())  # type: ignore[arg-type]
        teardown_done: list[bool] = []

        async def connect_and_offer() -> None:
            assert stream._teardown_task is not None
            teardown_done.append(stream._teardown_task.done())
            stream._answered.set()

        stream._connect_and_offer = connect_and_offer  # type: ignore[method-assign]
        task = asyncio.ensure_future(stream.start())
        try:
            for _ in range(5):
                await asyncio.sleep(0)
            assert teardown_done == []

            release.set()
            await asyncio.wait_for(task, timeout=1)
            assert teardown_done == [True]
        finally:
            release.set()
            await _cancel_pending(task)
        await stream.stop()

    async def test_stop_bounded_when_close_hangs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test stop() is not held up by a socket close that hangs."""
        monkeypatch.setattr(camera, "WS_CLOSE_TIMEOUT", 0.05)

        class _HangingCloseWebSocket(_FakeWebSocket):
            async def close(self) -> None:
                await asyncio.Event().wait()

        stream = CameraStream(_fake_client([]))
        stream._ws = _HangingCloseWebSocket([])
        await asyncio.wait_for(stream.stop(), timeout=1)
        assert stream._ws is None


class TestCameraStreamTracks:
    """Tests for delivering track frames to callbacks."""

    async def test_callback_registered_after_track(self) -> None:
        """Test a callback registered after the track arrived gets its frames.

        Tracks arrive while ``start()`` waits for the answer, i.e. before an
        ``async with`` body can register callbacks.
        """
        if not camera.HAS_AIORTC:
            pytest.skip("aiortc not installed")
        stream = CameraStream(_fake_client([]))
        frames: asyncio.Queue[int] = asyncio.Queue()
        for frame in (1, 2, 3):
            frames.put_nowait(frame)

        # what the peer connection's "track" handler does
        stream._tracks["video"] = SimpleNamespace(kind="video", recv=frames.get)
        stream._start_consumer("video")
        assert not stream._media_tasks  # no callback yet: not consumed

        received: list[int] = []
        stream.on_video_frame(received.append)
        stream.on_video_frame(received.append)  # re-registering adds no consumer
        for _ in range(5):
            await asyncio.sleep(0)

        assert received == [1, 2, 3]
        assert len(stream._media_tasks) == 1
        await stream.stop()


class TestCameraClientErrorFallbacks:
    """Tests that API errors degrade per the documented contracts."""

    @staticmethod
    def _failing_session(error: Exception) -> Any:
        session = SimpleNamespace()

        async def _raise(*args: Any, **kwargs: Any) -> Any:
            raise error

        session.get = _raise
        session.patch = _raise
        session.post = _raise
        return session

    async def test_get_videos_invalid_command_returns_empty(self) -> None:
        """Test HTTP 500 (InvalidCommandException) returns [] from get_videos."""
        client = CameraClient(
            session=self._failing_session(InvalidCommandException("server error")),
            device_id=CAMERA_DEVICE_ID,
        )
        assert await client.get_videos() == []
        assert await client.get_events() == []

    async def test_get_video_settings_invalid_command_returns_none(self) -> None:
        """Test HTTP 500 (InvalidCommandException) returns None from settings."""
        client = CameraClient(
            session=self._failing_session(InvalidCommandException("server error")),
            device_id=CAMERA_DEVICE_ID,
        )
        assert await client.get_video_settings() is None
        assert await client.get_audio_settings() is None
        assert await client.get_camera_info() is None

    async def test_get_camera_canvas_null_streams(self) -> None:
        """Test a null ``streams`` value yields None instead of raising."""
        session = SimpleNamespace()

        async def _settings(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "reportedSettings": [
                    {"settingsType": "videoSettings", "data": {"streams": None}}
                ]
            }

        session.get = _settings
        client = CameraClient(session=session, device_id=CAMERA_DEVICE_ID)  # type: ignore[arg-type]
        assert await client.get_camera_canvas() is None

    async def test_get_video_settings_null_envelope(self) -> None:
        """Test a null ``reportedSettings`` value yields None instead of raising."""
        session = SimpleNamespace()

        async def _settings(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"reportedSettings": None}

        session.get = _settings
        client = CameraClient(session=session, device_id=CAMERA_DEVICE_ID)  # type: ignore[arg-type]
        assert await client.get_video_settings() is None
        assert await client.get_camera_canvas() is None

    async def test_set_audio_enabled_invalid_command_returns_false(self) -> None:
        """Test HTTP 500 (InvalidCommandException) returns False from setters."""
        client = CameraClient(
            session=self._failing_session(InvalidCommandException("server error")),
            device_id=CAMERA_DEVICE_ID,
        )
        assert await client.set_audio_enabled(True) is False
        assert await client.set_camera_canvas(CAMERA_CANVAS_FRONT) is False
        with pytest.raises(InvalidCommandException):
            await client.validate_device_ownership()
        assert await client.get_camera_canvas() is None
        assert await client.get_camera_status() is None

    async def test_generate_session_wraps_invalid_command(self) -> None:
        """Test generate_session wraps InvalidCommandException."""
        client = CameraClient(
            session=self._failing_session(InvalidCommandException("server error")),
            device_id=CAMERA_DEVICE_ID,
        )
        with pytest.raises(CameraStreamException, match="Failed to generate"):
            await client.generate_session()

    @pytest.mark.parametrize(("status", "owned"), [(401, False), (403, False)])
    async def test_validate_device_ownership_refused(
        self, status: int, owned: bool
    ) -> None:
        """Test 401/403 from the ownership check mean "not your camera"."""
        client = CameraClient(
            session=self._failing_session(self._response_error(status)),
            device_id=CAMERA_DEVICE_ID,
        )
        assert await client.validate_device_ownership() is owned

    async def test_validate_device_ownership_empty_body_without_json_type(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test an empty 200 not labelled as JSON still means "owned"."""
        mock_aiointercept.post(
            f"{CAMERA_INVENTORY_API}/prod/v1/auth/validate-token",
            body="",
            content_type="application/octet-stream",
            repeat=True,
        )
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
        )
        assert await client.validate_device_ownership() is True

        await mock_account.disconnect()

    @pytest.mark.parametrize("status", [404, 429, 503])
    async def test_validate_device_ownership_other_errors_raise(
        self, status: int
    ) -> None:
        """Test other HTTP errors raise instead of looking like "not owned"."""
        client = CameraClient(
            session=self._failing_session(self._response_error(status)),
            device_id=CAMERA_DEVICE_ID,
        )
        with pytest.raises(ClientResponseError) as err:
            await client.validate_device_ownership()
        assert err.value.status == status

    @staticmethod
    def _response_error(status: int) -> ClientResponseError:
        url = URL("https://camera.example/validate-token")
        request_info = RequestInfo(
            url=url,
            method="POST",
            headers=CIMultiDictProxy(CIMultiDict()),
            real_url=url,
        )
        return ClientResponseError(
            request_info=request_info, history=(), status=status, message="error"
        )

    async def test_generate_session_wraps_client_response_error(self) -> None:
        """Test generate_session wraps ClientResponseError (e.g. 403)."""
        request_info = RequestInfo(
            url=URL("https://watford.example/session"),
            method="GET",
            headers=CIMultiDictProxy(CIMultiDict()),
            real_url=URL("https://watford.example/session"),
        )
        error = ClientResponseError(
            request_info=request_info, history=(), status=403, message="Forbidden"
        )
        client = CameraClient(
            session=self._failing_session(error),
            device_id=CAMERA_DEVICE_ID,
        )
        with pytest.raises(CameraStreamException, match="Failed to generate"):
            await client.generate_session()


class TestCameraAudioReconciliation:
    """Tests for refresh_camera_audio_enabled."""

    async def test_refresh_camera_audio_enabled(
        self,
        mock_account: Account,
        mock_aiointercept: aiointercept,
    ) -> None:
        """Test reconciling the audio cache from reported settings."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        # conftest serves CAMERA_AUDIO_SETTINGS_RESPONSE (mute: True) for
        # reported audioSettings
        assert await robot.refresh_camera_audio_enabled() is False
        assert robot.camera_audio_enabled is False

        await robot._account.disconnect()

    async def test_refresh_camera_audio_unmuted(
        self,
        mock_account: Account,
    ) -> None:
        """Test an unmuted reported-settings response enables the cache."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        async def _settings(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "reportedSettings": [
                    {
                        "settingsType": "audioSettings",
                        "data": {"audio_in": {"global": {"mute": False}}},
                    }
                ]
            }

        client._session = SimpleNamespace(get=_settings)  # type: ignore[assignment]
        assert await robot.refresh_camera_audio_enabled() is True
        assert robot.camera_audio_enabled is True

        await robot._account.disconnect()

    async def test_refresh_camera_audio_unknown_shape(
        self,
        mock_account: Account,
    ) -> None:
        """Test an unrecognized settings shape returns None and leaves cache."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        async def _settings(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"something": "else"}

        client._session = SimpleNamespace(get=_settings)  # type: ignore[assignment]
        assert await robot.refresh_camera_audio_enabled() is None

        await robot._account.disconnect()


class TestLocalTimezoneName:
    """Tests for local_timezone_name()."""

    def test_tz_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid IANA ``TZ`` (with optional leading colon) wins."""
        monkeypatch.setenv("TZ", ":Australia/Sydney")
        assert local_timezone_name() == "Australia/Sydney"

    def test_localtime_symlink(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to the /etc/localtime symlink target."""
        monkeypatch.setenv("TZ", "AEST-10")  # POSIX string, not an IANA key
        monkeypatch.setattr(
            "pylitterbot.camera.os.path.realpath",
            lambda _: "/var/db/timezone/zoneinfo/America/Detroit",
        )
        assert local_timezone_name() == "America/Detroit"

    def test_fallback_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without a usable TZ or symlink, UTC is used."""
        monkeypatch.delenv("TZ", raising=False)
        monkeypatch.setattr(
            "pylitterbot.camera.os.path.realpath", lambda _: "/etc/localtime"
        )
        assert local_timezone_name() == "UTC"

    @pytest.mark.parametrize(
        "tz", ["EST5EDT,M3.2.0,M11.1.0", "<+11>-11", "UTC0", "/etc/localtime"]
    )
    def test_posix_tz_strings_ignored(
        self, monkeypatch: pytest.MonkeyPatch, tz: str
    ) -> None:
        """``TZ`` values that aren't Area/Location names are skipped."""
        monkeypatch.setenv("TZ", tz)
        monkeypatch.setattr(
            "pylitterbot.camera.os.path.realpath", lambda _: "/etc/localtime"
        )
        assert local_timezone_name() == "UTC"

    def test_etc_offset_zone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """IANA names containing offsets, like ``Etc/GMT-10``, are accepted."""
        monkeypatch.setenv("TZ", "Etc/GMT-10")
        assert local_timezone_name() == "Etc/GMT-10"

    def test_bare_utc_tz_wins_over_localtime(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``TZ=UTC`` overrides a different /etc/localtime zone."""
        monkeypatch.setenv("TZ", "UTC")
        monkeypatch.setattr(
            "pylitterbot.camera.os.path.realpath",
            lambda _: "/usr/share/zoneinfo/America/Detroit",
        )
        assert local_timezone_name() == "UTC"
