"""Test camera module."""

# pylint: disable=protected-access
from __future__ import annotations

import asyncio
import json
from base64 import b64decode, b64encode
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import WSMsgType
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.camera import (
    CAMERA_CANVAS_FRONT,
    CAMERA_CANVAS_GLOBE,
    CAMERA_INVENTORY_API,
    CAMERA_SETTINGS_API,
    HAS_AIORTC,
    WATFORD_API,
    CameraClient,
    CameraSession,
    CameraSignalingRelay,
    CameraStream,
    VideoClip,
)

if HAS_AIORTC:
    from aiortc.sdp import candidate_from_sdp
from pylitterbot.exceptions import (
    CameraNotAvailableException,
    CameraStreamException,
    InvalidCommandException,
)
from pylitterbot.robot.litterrobot5 import LitterRobot5

from .common import (
    CAMERA_DEVICE_ID,
    CAMERA_EVENTS_RESPONSE,
    CAMERA_INFO_RESPONSE,
    CAMERA_SESSION_RESPONSE,
    CAMERA_VIDEO_SETTINGS_RESPONSE,
    CAMERA_VIDEOS_RESPONSE,
    LITTER_ROBOT_5_DATA,
    LITTER_ROBOT_5_PRO_DATA,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# CameraSession dataclass tests
# ---------------------------------------------------------------------------


class TestCameraSession:
    """Tests for CameraSession dataclass."""

    def test_from_response(self) -> None:
        """Test CameraSession creation from API response."""
        session = CameraSession.from_response(CAMERA_SESSION_RESPONSE)
        assert session.session_id == "test-session-id-1234"
        assert session.session_token == "test-session-token-abcdef"
        assert session.session_expiration is not None
        assert "accessToken=test-session-token-abcdef" in session.signaling_url
        assert len(session.turn_servers) == 1
        assert session.turn_servers[0]["username"] == "turn-user"
        assert session.raw == CAMERA_SESSION_RESPONSE

    def test_from_response_missing_fields(self) -> None:
        """Test CameraSession with minimal data."""
        session = CameraSession.from_response({})
        assert session.session_id == ""
        assert session.session_token == ""
        assert session.session_expiration is None
        assert session.turn_servers == []

    def test_from_response_dict_turn_creds(self) -> None:
        """Test CameraSession when turnCredentials is a dict (not list)."""
        data = {
            **CAMERA_SESSION_RESPONSE,
            "turnCredentials": {
                "urls": ["turn:example.com:443"],
                "username": "u",
                "credential": "c",
            },
        }
        session = CameraSession.from_response(data)
        assert len(session.turn_servers) == 1

    def test_from_response_ice_servers_key(self) -> None:
        """Test CameraSession when iceServers is used instead of turnCredentials."""
        data = {
            "sessionId": "s1",
            "sessionToken": "t1",
            "iceServers": [
                {"urls": "turn:ice.example.com", "username": "u", "credential": "c"}
            ],
        }
        session = CameraSession.from_response(data)
        assert len(session.turn_servers) == 1


# ---------------------------------------------------------------------------
# VideoClip dataclass tests
# ---------------------------------------------------------------------------


class TestVideoClip:
    """Tests for VideoClip dataclass."""

    def test_from_response(self) -> None:
        """Test VideoClip creation from API response."""
        clip = VideoClip.from_response(CAMERA_VIDEOS_RESPONSE[0])
        assert clip.id == "video-001"
        assert clip.thumbnail_url == "https://example.com/thumb1.jpg"
        assert clip.event_type == "PET_VISIT"
        assert clip.duration == 15.5
        assert clip.created_at is not None

    def test_from_response_alternate_keys(self) -> None:
        """Test VideoClip with alternate key names."""
        data = {
            "videoId": "v-alt",
            "thumbnail": "https://example.com/alt.jpg",
            "type": "MOTION",
            "timestamp": "2025-12-01T10:00:00Z",
        }
        clip = VideoClip.from_response(data)
        assert clip.id == "v-alt"
        assert clip.thumbnail_url == "https://example.com/alt.jpg"
        assert clip.event_type == "MOTION"
        assert clip.created_at is not None

    def test_from_response_empty(self) -> None:
        """Test VideoClip with empty response."""
        clip = VideoClip.from_response({})
        assert clip.id == ""
        assert clip.thumbnail_url is None
        assert clip.event_type is None


# ---------------------------------------------------------------------------
# CameraClient REST tests
# ---------------------------------------------------------------------------


class TestCameraClient:
    """Tests for CameraClient REST API calls."""

    async def test_generate_session(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
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

    async def test_generate_session_auto_start_false(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test generating a session with autoStart=false."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
        )
        session = await client.generate_session(auto_start=False)
        assert isinstance(session, CameraSession)

    async def test_get_video_settings(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test fetching video settings."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        settings = await client.get_video_settings()
        assert settings is not None
        assert "reportedSettings" in settings

    async def test_set_camera_canvas(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test setting camera canvas."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        result = await client.set_camera_canvas(CAMERA_CANVAS_FRONT)
        assert result is True

    async def test_get_audio_settings(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test fetching audio settings."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        settings = await client.get_audio_settings()
        assert settings is not None

    async def test_get_camera_info(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test fetching camera info."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        info = await client.get_camera_info()
        assert info is not None
        assert info["deviceId"] == CAMERA_DEVICE_ID

    async def test_get_videos(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
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
        assert videos[0].id == "video-001"

    async def test_get_videos_with_date(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test fetching videos with date filter."""
        client = CameraClient(
            session=mock_account.session,
            device_id=CAMERA_DEVICE_ID,
            api_key="test-key",
        )
        videos = await client.get_videos(date="2025-12-01")
        assert isinstance(videos, list)

    async def test_get_events(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
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


# ---------------------------------------------------------------------------
# LR5 camera convenience method tests
# ---------------------------------------------------------------------------


class TestLR5CameraMethods:
    """Tests for LitterRobot5 camera convenience methods."""

    async def test_has_camera_pro(
        self,
        mock_account: Account,
    ) -> None:
        """Test has_camera returns True for Pro model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        assert robot.has_camera is True

    async def test_has_camera_standard(
        self,
        mock_account: Account,
    ) -> None:
        """Test has_camera returns False for standard model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
        assert robot.has_camera is False

    async def test_camera_metadata_pro(
        self,
        mock_account: Account,
    ) -> None:
        """Test camera_metadata returns dict for Pro model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        assert robot.camera_metadata is not None
        assert robot.camera_metadata["deviceId"] == CAMERA_DEVICE_ID

    async def test_get_camera_client(
        self,
        mock_account: Account,
    ) -> None:
        """Test get_camera_client returns a CameraClient."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()
        assert isinstance(client, CameraClient)
        assert client.device_id == CAMERA_DEVICE_ID

    async def test_get_camera_client_raises_no_camera(
        self,
        mock_account: Account,
    ) -> None:
        """Test get_camera_client raises for standard model."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
        with pytest.raises(CameraNotAvailableException):
            robot.get_camera_client()

    async def test_get_camera_session(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test get_camera_session returns a CameraSession."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        session = await robot.get_camera_session()
        assert isinstance(session, CameraSession)

    async def test_get_camera_videos(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test get_camera_videos returns video clips."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        videos = await robot.get_camera_videos()
        assert len(videos) == 2
        assert isinstance(videos[0], VideoClip)

    async def test_get_camera_video_settings(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test get_camera_video_settings returns settings dict."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        settings = await robot.get_camera_video_settings()
        assert settings is not None
        assert "reportedSettings" in settings

    async def test_set_camera_view_front(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test set_camera_view with 'front'."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        result = await robot.set_camera_view("front")
        assert result is True

    async def test_set_camera_view_globe(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test set_camera_view with 'globe'."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        result = await robot.set_camera_view("globe")
        assert result is True

    async def test_set_camera_view_invalid(
        self,
        mock_account: Account,
    ) -> None:
        """Test set_camera_view with invalid view name raises."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        with pytest.raises(InvalidCommandException, match="Invalid camera view"):
            await robot.set_camera_view("rear")


# ---------------------------------------------------------------------------
# CameraSignalingRelay tests
# ---------------------------------------------------------------------------


class _AsyncWSIterator:
    """Async iterator that yields mock WebSocket messages."""

    def __init__(self, messages: list[Any]) -> None:
        self._messages = list(messages)
        self._index = 0

    def __aiter__(self) -> _AsyncWSIterator:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._index]
        self._index += 1
        return msg


class TestCameraSignalingRelay:
    """Tests for CameraSignalingRelay signaling-only WebRTC relay."""

    async def test_start_sends_offer_and_relays_answer(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test that start connects WS, sends b64 offer, and relays answer."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        mock_session = CameraSession.from_response(CAMERA_SESSION_RESPONSE)

        answer_sdp = "v=0\r\no=- 12345 2 IN IP4 127.0.0.1\r\n"
        encoded_answer = b64encode(answer_sdp.encode()).decode()

        # Build a mock WS that yields one answer message then stops
        answer_msg = MagicMock()
        answer_msg.type = WSMsgType.TEXT
        answer_msg.json.return_value = {"type": "answer", "sdp": encoded_answer}

        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.ping = AsyncMock()
        mock_ws.__aiter__ = lambda self: _AsyncWSIterator([answer_msg])

        mock_websession = MagicMock()
        mock_websession.ws_connect = AsyncMock(return_value=mock_ws)

        original_ws = client._session._websession
        client._session._websession = mock_websession

        try:
            with patch.object(
                client, "generate_session", new=AsyncMock(return_value=mock_session)
            ):
                relay = CameraSignalingRelay(client)
                received_answer = []
                received_candidates = []

                session = await relay.start(
                    offer_sdp="v=0\r\n",
                    on_answer=lambda sdp: received_answer.append(sdp),
                    on_candidate=lambda c: received_candidates.append(c),
                )

                assert isinstance(session, CameraSession)
                assert session.session_token == "test-session-token-abcdef"

                # Verify offer was base64 encoded and sent
                mock_ws.send_json.assert_awaited_once()
                call_args = mock_ws.send_json.call_args[0][0]
                assert call_args["type"] == "offer"
                assert b64decode(call_args["sdp"]).decode() == "v=0\r\n"

                # Wait for receive loop to process the answer
                await asyncio.sleep(0.1)

                assert len(received_answer) == 1
                assert received_answer[0] == answer_sdp

                await relay.close()
        finally:
            client._session._websession = original_ws

    async def test_relays_ice_candidates(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test that ICE candidates from camera are relayed to callback."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        mock_session = CameraSession.from_response(CAMERA_SESSION_RESPONSE)

        candidate_msg = MagicMock()
        candidate_msg.type = WSMsgType.TEXT
        candidate_msg.json.return_value = {
            "type": "candidate",
            "candidate": "candidate:1 1 UDP 2122260223 192.168.1.1 50000 typ host",
            "sdpMid": "0",
            "sdpMLineIndex": 0,
        }

        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.ping = AsyncMock()
        mock_ws.__aiter__ = lambda self: _AsyncWSIterator([candidate_msg])

        mock_websession = MagicMock()
        mock_websession.ws_connect = AsyncMock(return_value=mock_ws)

        original_ws = client._session._websession
        client._session._websession = mock_websession

        try:
            with patch.object(
                client, "generate_session", new=AsyncMock(return_value=mock_session)
            ):
                relay = CameraSignalingRelay(client)
                received_candidates = []

                await relay.start(
                    offer_sdp="v=0\r\n",
                    on_answer=lambda sdp: None,
                    on_candidate=lambda c: received_candidates.append(c),
                )

                await asyncio.sleep(0.1)

                assert len(received_candidates) == 1
                assert "candidate:1" in received_candidates[0]["candidate"]
                assert received_candidates[0]["sdpMid"] == "0"

                await relay.close()
        finally:
            client._session._websession = original_ws

    async def test_send_candidate_forwards_to_ws(
        self,
        mock_account: Account,
    ) -> None:
        """Test that send_candidate forwards browser ICE candidate to camera."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        relay = CameraSignalingRelay(client)
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        relay._ws = mock_ws

        await relay.send_candidate(
            {
                "candidate": "candidate:2 1 UDP 1686052607 1.2.3.4 50001 typ srflx",
                "sdpMid": "0",
                "sdpMLineIndex": 0,
            }
        )

        mock_ws.send_json.assert_awaited_once()
        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "candidate"
        assert "candidate:2" in sent["candidate"]

    async def test_close_cleans_up(
        self,
        mock_account: Account,
    ) -> None:
        """Test that close cancels tasks and closes WebSocket."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        relay = CameraSignalingRelay(client)
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        relay._ws = mock_ws

        # Create mock tasks
        relay._ping_task = asyncio.ensure_future(asyncio.sleep(100))
        relay._receive_task = asyncio.ensure_future(asyncio.sleep(100))

        await relay.close()

        assert relay._closed is True
        mock_ws.close.assert_awaited_once()
        assert relay._ping_task.done()
        assert relay._receive_task.done()

    async def test_start_after_close_raises(
        self,
        mock_account: Account,
    ) -> None:
        """Test that starting a closed relay raises."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        relay = CameraSignalingRelay(client)
        relay._closed = True

        with pytest.raises(CameraStreamException, match="closed"):
            await relay.start(
                offer_sdp="v=0\r\n",
                on_answer=lambda sdp: None,
                on_candidate=lambda c: None,
            )

    async def test_session_property(
        self,
        mock_account: Account,
    ) -> None:
        """Test session property returns None before start."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        relay = CameraSignalingRelay(client)
        assert relay.session is None


# ---------------------------------------------------------------------------
# CameraStream tests (mock aiortc)
# ---------------------------------------------------------------------------


class TestCameraStream:
    """Tests for CameraStream WebRTC functionality."""

    def test_import_guard_no_aiortc(self) -> None:
        """Test that CameraStream raises ImportError when aiortc is missing."""
        with patch("pylitterbot.camera.HAS_AIORTC", False):
            mock_client = MagicMock()
            with pytest.raises(ImportError, match="aiortc"):
                CameraStream(mock_client)

    @pytest.mark.skipif(not HAS_AIORTC, reason="aiortc not installed")
    async def test_context_manager_lifecycle(
        self,
        mock_account: Account,
        mock_aioresponse: aioresponses,
    ) -> None:
        """Test CameraStream start/stop lifecycle via context manager."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()

        mock_pc = MagicMock()
        mock_pc.connectionState = "new"
        mock_pc.createOffer = AsyncMock(
            return_value=MagicMock(sdp="v=0\r\n", type="offer")
        )
        mock_pc.setLocalDescription = AsyncMock()
        mock_pc.setRemoteDescription = AsyncMock()
        mock_pc.addIceCandidate = AsyncMock()
        mock_pc.close = AsyncMock()
        mock_pc.addTransceiver = MagicMock()

        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.ping = AsyncMock()
        mock_ws.__aiter__ = MagicMock(return_value=iter([]))

        mock_session = CameraSession.from_response(CAMERA_SESSION_RESPONSE)

        mock_websession = MagicMock()
        mock_websession.ws_connect = AsyncMock(return_value=mock_ws)

        # Replace the session's internal _websession so the websession
        # property returns our mock.
        original_ws = client._session._websession
        client._session._websession = mock_websession

        with (
            patch("pylitterbot.camera.RTCPeerConnection", return_value=mock_pc),
            patch("pylitterbot.camera.RTCConfiguration"),
            patch("pylitterbot.camera.RTCIceServer"),
            patch.object(
                client, "generate_session", new=AsyncMock(return_value=mock_session)
            ),
        ):
            try:
                stream = CameraStream(client)
                await stream.start()

                assert stream._pc is mock_pc
                assert stream._ws is mock_ws
                mock_pc.createOffer.assert_awaited_once()
                mock_pc.setLocalDescription.assert_awaited_once()
                mock_ws.send_json.assert_awaited_once()

                # Verify the offer SDP was base64 encoded
                call_args = mock_ws.send_json.call_args[0][0]
                assert call_args["type"] == "offer"
                decoded = b64decode(call_args["sdp"]).decode()
                assert decoded == "v=0\r\n"

                await stream.stop()
                mock_pc.close.assert_awaited_once()
            finally:
                client._session._websession = original_ws

    async def test_video_frame_callback(self) -> None:
        """Test on_video_frame registers callback."""
        with patch("pylitterbot.camera.HAS_AIORTC", True):
            mock_client = MagicMock()
            stream = CameraStream.__new__(CameraStream)
            stream._client = mock_client
            stream._kwargs = {}
            stream._session = None
            stream._pc = None
            stream._ws = None
            stream._ping_task = None
            stream._receive_task = None
            stream._video_callback = None
            stream._audio_callback = None
            stream._state_callback = None
            stream._connected = asyncio.Event()
            stream._stopped = False

            callback = MagicMock()
            stream.on_video_frame(callback)
            assert stream._video_callback is callback

    async def test_audio_frame_callback(self) -> None:
        """Test on_audio_frame registers callback."""
        with patch("pylitterbot.camera.HAS_AIORTC", True):
            mock_client = MagicMock()
            stream = CameraStream.__new__(CameraStream)
            stream._client = mock_client
            stream._kwargs = {}
            stream._session = None
            stream._pc = None
            stream._ws = None
            stream._ping_task = None
            stream._receive_task = None
            stream._video_callback = None
            stream._audio_callback = None
            stream._state_callback = None
            stream._connected = asyncio.Event()
            stream._stopped = False

            callback = MagicMock()
            stream.on_audio_frame(callback)
            assert stream._audio_callback is callback

    async def test_connection_state_callback(self) -> None:
        """Test on_connection_state_change registers callback."""
        with patch("pylitterbot.camera.HAS_AIORTC", True):
            mock_client = MagicMock()
            stream = CameraStream.__new__(CameraStream)
            stream._client = mock_client
            stream._kwargs = {}
            stream._session = None
            stream._pc = None
            stream._ws = None
            stream._ping_task = None
            stream._receive_task = None
            stream._video_callback = None
            stream._audio_callback = None
            stream._state_callback = None
            stream._connected = asyncio.Event()
            stream._stopped = False

            callback = MagicMock()
            stream.on_connection_state_change(callback)
            assert stream._state_callback is callback

    async def test_wait_for_connection_timeout(self) -> None:
        """Test wait_for_connection times out correctly."""
        with patch("pylitterbot.camera.HAS_AIORTC", True):
            stream = CameraStream.__new__(CameraStream)
            stream._connected = asyncio.Event()
            stream._stopped = False

            result = await stream.wait_for_connection(timeout=0.1)
            assert result is False

    async def test_wait_for_connection_success(self) -> None:
        """Test wait_for_connection succeeds when event is set."""
        with patch("pylitterbot.camera.HAS_AIORTC", True):
            stream = CameraStream.__new__(CameraStream)
            stream._connected = asyncio.Event()
            stream._stopped = False
            stream._connected.set()

            result = await stream.wait_for_connection(timeout=1.0)
            assert result is True

    @pytest.mark.skipif(not HAS_AIORTC, reason="aiortc not installed")
    async def test_handles_base64_answer(self) -> None:
        """Test that base64-encoded SDP answers are properly decoded."""
        stream = CameraStream.__new__(CameraStream)
        stream._stopped = False

        mock_pc = MagicMock()
        mock_pc.setRemoteDescription = AsyncMock()
        stream._pc = mock_pc

        # Simulate a base64-encoded answer
        raw_sdp = "v=0\r\no=- 12345 2 IN IP4 127.0.0.1\r\n"
        encoded = b64encode(raw_sdp.encode()).decode()

        await stream._handle_signaling_message(
            {
                "type": "answer",
                "sdp": encoded,
            }
        )

        mock_pc.setRemoteDescription.assert_awaited_once()
        call_args = mock_pc.setRemoteDescription.call_args[0][0]
        assert call_args.sdp == raw_sdp
        assert call_args.type == "answer"

    @pytest.mark.skipif(not HAS_AIORTC, reason="aiortc not installed")
    async def test_handles_ice_candidate(self) -> None:
        """Test ICE candidate handling."""
        stream = CameraStream.__new__(CameraStream)
        stream._stopped = False

        mock_pc = MagicMock()
        mock_pc.addIceCandidate = AsyncMock()
        stream._pc = mock_pc

        # Use a valid ICE candidate SDP string
        await stream._handle_signaling_message(
            {
                "type": "candidate",
                "candidate": "candidate:1 1 UDP 2122260223 192.168.1.1 50000 typ host",
                "sdpMid": "0",
                "sdpMLineIndex": 0,
            }
        )

        mock_pc.addIceCandidate.assert_awaited_once()
        # Verify the parsed candidate has correct sdpMid
        call_args = mock_pc.addIceCandidate.call_args[0][0]
        assert call_args.sdpMid == "0"
        assert call_args.sdpMLineIndex == 0

    @pytest.mark.skipif(not HAS_AIORTC, reason="aiortc not installed")
    async def test_handles_empty_candidate(self) -> None:
        """Test that empty ICE candidate is ignored."""
        stream = CameraStream.__new__(CameraStream)
        stream._stopped = False

        mock_pc = MagicMock()
        mock_pc.addIceCandidate = AsyncMock()
        stream._pc = mock_pc

        await stream._handle_signaling_message(
            {
                "type": "candidate",
                "candidate": "",
            }
        )

        mock_pc.addIceCandidate.assert_not_awaited()

    @pytest.mark.skipif(not HAS_AIORTC, reason="aiortc not installed")
    async def test_start_stopped_raises(
        self,
        mock_account: Account,
    ) -> None:
        """Test that starting a stopped stream raises."""
        robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
        client = robot.get_camera_client()
        stream = CameraStream(client)
        stream._stopped = True
        with pytest.raises(CameraStreamException, match="stopped"):
            await stream.start()

    @pytest.mark.skipif(not HAS_AIORTC, reason="aiortc not installed")
    def test_build_ice_servers(self) -> None:
        """Test ICE server construction from TURN credentials."""
        turn_creds: list[dict[str, Any]] = [
            {
                "urls": ["turn:turn.example.com:443?transport=tcp"],
                "username": "user",
                "credential": "pass",
            },
            {
                "uris": "turn:turn2.example.com:443",
                "username": "user2",
                "credential": "pass2",
            },
        ]
        servers = CameraStream._build_ice_servers(turn_creds)
        # STUN + 2 TURN servers
        assert len(servers) == 3
