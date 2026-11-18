"""Test camera module."""

# pylint: disable=protected-access
from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from aiohttp import ClientResponseError, RequestInfo, WSMsgType
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
    VideoClip,
    VideoPlayback,
    _decode_sdp,
    _parse_signaling_message,
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
        await sending.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert ws.closed
        assert relay.session is None

    async def test_relay_raises_when_never_answered(self) -> None:
        """Test the relay gives up after ANSWER_ATTEMPTS unanswered offers."""
        sockets = [_FakeWebSocket([]), _FakeWebSocket([])]
        relay = CameraSignalingRelay(_fake_client(sockets))

        with pytest.raises(CameraStreamException, match="did not answer"):
            await relay.start("v=0 offer", lambda a: None, lambda c: None)

        assert all(ws.closed for ws in sockets)
        assert relay.session is None

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

    async def test_set_audio_enabled_invalid_command_returns_false(self) -> None:
        """Test HTTP 500 (InvalidCommandException) returns False from setters."""
        client = CameraClient(
            session=self._failing_session(InvalidCommandException("server error")),
            device_id=CAMERA_DEVICE_ID,
        )
        assert await client.set_audio_enabled(True) is False
        assert await client.set_camera_canvas(CAMERA_CANVAS_FRONT) is False
        assert await client.validate_device_ownership() is False
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
