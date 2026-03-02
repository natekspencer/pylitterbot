"""Camera support for Litter-Robot 5 Pro.

Provides REST API access to camera sessions, settings, videos, and events
via `CameraClient`, and WebRTC live streaming via `CameraStream`.

WebRTC streaming requires the optional ``aiortc`` dependency::

    pip install pylitterbot[camera]
"""

from __future__ import annotations

import asyncio
import logging
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from aiohttp import ClientResponseError, WSMsgType

from .exceptions import CameraStreamException
from .utils import to_timestamp

if TYPE_CHECKING:
    from .session import Session

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WATFORD_API = "https://watford.ienso-dev.com"
CAMERA_SETTINGS_API = "https://7mnuil943l.execute-api.us-east-1.amazonaws.com"
CAMERA_INVENTORY_API = "https://rrntg65uwf.execute-api.us-east-1.amazonaws.com"

CAMERA_CANVAS_FRONT = "sensor_0_1080p"
CAMERA_CANVAS_GLOBE = "sensor_1_720p"
CAMERA_CANVAS_LABELS: dict[str, str] = {
    CAMERA_CANVAS_FRONT: "Front Camera (1080p)",
    CAMERA_CANVAS_GLOBE: "Globe Camera (720p)",
}

GENERATE_SESSION_PATH = "api/device-manager/client/generate-session"
SIGNALING_PATH = "api/signaling"

PING_INTERVAL = 5  # seconds – ping frequently to prevent server idle timeout (~18s)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CameraSession:
    """Represents a camera streaming session with TURN credentials."""

    session_id: str
    session_token: str
    session_expiration: datetime | None
    signaling_url: str
    turn_servers: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> CameraSession:
        """Create a CameraSession from the generate-session API response."""
        session_token = data.get("sessionToken", "")
        turn_creds = (
            data.get("turnCredentials")
            or data.get("iceServers")
            or data.get("turnServer")
            or []
        )
        if isinstance(turn_creds, dict):
            turn_creds = [turn_creds]

        signaling_url = (
            f"wss://watford.ienso-dev.com/{SIGNALING_PATH}?accessToken={session_token}"
        )

        return cls(
            session_id=data.get("sessionId", ""),
            session_token=session_token,
            session_expiration=to_timestamp(data.get("sessionExpiration")),
            signaling_url=signaling_url,
            turn_servers=turn_creds,
            raw=data,
        )


@dataclass
class VideoClip:
    """Represents a recorded camera video clip."""

    id: str
    thumbnail_url: str | None
    event_type: str | None
    duration: float | None
    created_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> VideoClip:
        """Create a VideoClip from an API response item."""
        duration = data.get("duration")
        if duration is None and (hls := data.get("hlsDuration")):
            # Parse "MM:SS" format to seconds
            try:
                parts = str(hls).split(":")
                duration = (
                    int(parts[0]) * 60 + int(parts[1])
                    if len(parts) == 2
                    else float(hls)
                )
            except (ValueError, IndexError):
                duration = None
        return cls(
            id=str(data.get("id", data.get("videoId", ""))),
            thumbnail_url=(
                data.get("thumbnailUrl")
                or data.get("videoThumbnail")
                or data.get("thumbnail")
            ),
            event_type=data.get("eventType") or data.get("type"),
            duration=duration,
            created_at=to_timestamp(data.get("createdAt") or data.get("timestamp")),
            raw=data,
        )


# ---------------------------------------------------------------------------
# CameraClient — REST API (no aiortc dependency)
# ---------------------------------------------------------------------------


class CameraClient:
    """REST client for LR5 Pro camera APIs.

    Uses the account session for Bearer token auth.  Camera settings and
    inventory endpoints additionally require an ``x-api-key`` header.
    """

    def __init__(
        self,
        session: Session,
        device_id: str,
        *,
        api_key: str | None = None,
    ) -> None:
        """Initialize the camera client.

        Args:
            session: The authenticated pylitterbot session.
            device_id: The camera ``deviceId`` from robot ``cameraMetadata``.
            api_key: Optional x-api-key for settings/inventory endpoints.

        """
        self._session = session
        self._device_id = device_id
        self._api_key = api_key

    @property
    def device_id(self) -> str:
        """Return the camera device id."""
        return self._device_id

    def _settings_headers(self) -> dict[str, str]:
        """Return extra headers for camera settings/inventory endpoints."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    # -- Session -----------------------------------------------------------

    async def generate_session(self, *, auto_start: bool = True) -> CameraSession:
        """Create a camera streaming session.

        Returns TURN credentials and a signaling websocket URL.
        """
        url = f"{WATFORD_API}/{GENERATE_SESSION_PATH}/{self._device_id}"
        data = await self._session.get(
            url,
            params={"autoStart": "true" if auto_start else "false"},
        )
        if not isinstance(data, dict):
            raise CameraStreamException(
                "Failed to generate camera session: unexpected response"
            )
        return CameraSession.from_response(data)

    # -- Video settings ----------------------------------------------------

    async def get_video_settings(
        self, settings_type: str = "videoSettings"
    ) -> dict[str, Any] | None:
        """Fetch reported video settings for the camera."""
        url = (
            f"{CAMERA_SETTINGS_API}/prod/v1/cameras/"
            f"{self._device_id}/reported-settings/{settings_type}"
        )
        try:
            data = await self._session.get(url, headers=self._settings_headers())
        except ClientResponseError:
            return None
        return data if isinstance(data, dict) else None

    async def set_camera_canvas(self, canvas: str) -> bool:
        """Set the live-view canvas (camera view selection).

        Args:
            canvas: One of ``CAMERA_CANVAS_FRONT`` or ``CAMERA_CANVAS_GLOBE``.

        """
        from .utils import utcnow

        url = (
            f"{CAMERA_SETTINGS_API}/prod/v1/cameras/"
            f"{self._device_id}/desired-settings/videoSettings"
        )
        payload = {
            "streams": {"live-view": {"canvas": canvas}},
            "timestamp": utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        try:
            await self._session.patch(
                url, json=payload, headers=self._settings_headers()
            )
            return True
        except ClientResponseError:
            return False

    async def set_audio_enabled(self, enabled: bool) -> bool:
        """Enable or disable the camera microphone.

        Args:
            enabled: ``True`` to unmute, ``False`` to mute.

        """
        url = (
            f"{CAMERA_SETTINGS_API}/prod/v1/cameras/"
            f"{self._device_id}/desired-settings/audioSettings"
        )
        payload = {
            "audio_in": {"global": {"mute": not enabled}},
        }
        try:
            await self._session.patch(
                url, json=payload, headers=self._settings_headers()
            )
            return True
        except ClientResponseError:
            return False

    # -- Audio settings ----------------------------------------------------

    async def get_audio_settings(self) -> dict[str, Any] | None:
        """Fetch reported audio settings for the camera."""
        url = (
            f"{CAMERA_SETTINGS_API}/prod/v1/cameras/"
            f"{self._device_id}/reported-settings/audioSettings"
        )
        try:
            data = await self._session.get(url, headers=self._settings_headers())
        except ClientResponseError:
            return None
        return data if isinstance(data, dict) else None

    # -- Camera info -------------------------------------------------------

    async def get_camera_info(self) -> dict[str, Any] | None:
        """Fetch camera device information from the inventory API."""
        url = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{self._device_id}"
        try:
            data = await self._session.get(url, headers=self._settings_headers())
        except ClientResponseError:
            return None
        return data if isinstance(data, dict) else None

    # -- Videos ------------------------------------------------------------

    async def get_videos(
        self, date: str | None = None, limit: int | None = None
    ) -> list[VideoClip]:
        """Fetch recorded video clips.

        Args:
            date: Optional date string (YYYY-MM-DD) to filter videos.
            limit: Optional max number of results.

        """
        parts = [f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{self._device_id}/videos"]
        if date:
            parts.append(f"/{date}")
        url = "".join(parts)
        params: dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        try:
            data = await self._session.get(
                url,
                headers=self._settings_headers(),
                params=params or None,
            )
        except ClientResponseError:
            return []
        if not isinstance(data, list):
            return []
        return [
            VideoClip.from_response(item) for item in data if isinstance(item, dict)
        ]

    # -- Events ------------------------------------------------------------

    async def get_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Fetch camera events (AI detections, etc.).

        Args:
            limit: Optional max number of results.

        """
        url = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{self._device_id}/events"
        params: dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        try:
            data = await self._session.get(
                url,
                headers=self._settings_headers(),
                params=params or None,
            )
        except ClientResponseError:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# CameraSignalingRelay — Browser-to-camera WebRTC signaling (no aiortc)
# ---------------------------------------------------------------------------


class CameraSignalingRelay:
    """Signaling relay for browser-to-camera WebRTC.

    Unlike ``CameraStream`` (which creates its own RTCPeerConnection via
    aiortc), this class only handles signaling — forwarding SDP and ICE
    candidates between the browser and camera via the Watford signaling
    WebSocket. Designed for HA's camera platform where the browser is the
    WebRTC peer.
    """

    def __init__(self, client: CameraClient) -> None:
        """Initialize the signaling relay.

        Args:
            client: A ``CameraClient`` instance.

        """
        self._client = client
        self._session: CameraSession | None = None
        self._ws: Any | None = None  # aiohttp ClientWebSocketResponse
        self._ping_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._closed = False
        self._pending_candidates: list[dict[str, Any]] = []
        self._reconnect_task: asyncio.Task[None] | None = None

    @property
    def session(self) -> CameraSession | None:
        """Return the current camera session."""
        return self._session

    async def start(
        self,
        offer_sdp: str,
        on_answer: Callable[[str], None],
        on_candidate: Callable[[dict[str, Any]], None],
    ) -> CameraSession:
        """Connect to signaling WS, send offer, relay answer and ICE candidates.

        Args:
            offer_sdp: The browser's SDP offer (plain text, not base64).
            on_answer: Called with the decoded SDP answer from the camera.
            on_candidate: Called with ICE candidate dicts from the camera.

        Returns:
            The ``CameraSession`` with TURN credentials.

        """
        if self._closed:
            raise CameraStreamException("Relay has been closed")

        # 1. Generate camera session
        self._session = await self._client.generate_session()

        # 2. Connect to signaling WebSocket
        websession = self._client._session.websession  # noqa: SLF001
        self._ws = await websession.ws_connect(self._session.signaling_url)

        # 3. Send base64-encoded offer
        encoded_sdp = b64encode(offer_sdp.encode()).decode()
        _LOGGER.debug("Signaling relay: sending offer (%d bytes)", len(offer_sdp))
        await self._ws.send_json({"type": "offer", "sdp": encoded_sdp})

        # 3b. Flush any ICE candidates buffered before WS was connected
        if self._pending_candidates:
            _LOGGER.debug(
                "Signaling relay: flushing %d buffered ICE candidates",
                len(self._pending_candidates),
            )
            for msg in self._pending_candidates:
                await self._ws.send_json(msg)
            self._pending_candidates.clear()

        # 4. Start receive loop and keep-alive ping
        self._receive_task = asyncio.ensure_future(
            self._receive_loop(on_answer, on_candidate)
        )
        self._ping_task = asyncio.ensure_future(self._ping_loop())

        return self._session

    async def send_candidate(self, candidate: dict[str, Any]) -> None:
        """Forward a browser ICE candidate to the camera.

        If the signaling WebSocket is not yet connected, the candidate is
        buffered and will be flushed once ``start()`` completes.

        Args:
            candidate: ICE candidate dict with ``candidate``, ``sdpMid``,
                and ``sdpMLineIndex`` keys.

        """
        msg = {
            "type": "candidate",
            "candidate": candidate.get("candidate", ""),
            "sdpMid": candidate.get("sdpMid", "0"),
            "sdpMLineIndex": candidate.get("sdpMLineIndex", 0),
        }
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_json(msg)
                return
            except Exception:
                _LOGGER.debug(
                    "Signaling relay: send failed — buffering ICE candidate for reconnect",
                    exc_info=True,
                )

        _LOGGER.debug(
            "Signaling relay: WS closed — buffering ICE candidate for reconnect"
        )
        self._pending_candidates.append(msg)
        # If the WS closed after delivering the answer (expected server behavior),
        # try to reconnect and forward any buffered browser ICE candidates.
        if (
            self._session
            and not self._closed
            and (self._reconnect_task is None or self._reconnect_task.done())
        ):
            self._reconnect_task = asyncio.ensure_future(self._reconnect_and_flush())

    async def close(self) -> None:
        """Cancel tasks and close the signaling WebSocket."""
        self._closed = True

        for task in filter(
            None, [self._ping_task, self._receive_task, self._reconnect_task]
        ):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def _receive_loop(
        self,
        on_answer: Callable[[str], None],
        on_candidate: Callable[[dict[str, Any]], None],
    ) -> None:
        """Receive messages from the signaling WebSocket and relay them."""
        _LOGGER.debug("Signaling relay: receive loop started")
        try:
            async for msg in self._ws:  # type: ignore[union-attr]
                if self._closed:
                    break
                _LOGGER.debug("Signaling relay: received msg type=%s", msg.type)
                if msg.type == WSMsgType.TEXT:
                    data = msg.json()
                    msg_type = data.get("type", "")
                    _LOGGER.debug(
                        "Signaling relay: message type=%s keys=%s",
                        msg_type,
                        list(data.keys()),
                    )

                    if msg_type == "answer":
                        raw_sdp = data.get("payload") or data.get("sdp", "")
                        try:
                            sdp = b64decode(raw_sdp).decode()
                        except Exception:
                            sdp = raw_sdp
                        _LOGGER.debug(
                            "Signaling relay: received answer (%d bytes)",
                            len(sdp),
                        )
                        on_answer(sdp)

                    elif msg_type == "candidate" or "candidate" in data:
                        candidate_str = data.get("candidate", "")
                        if candidate_str:
                            _LOGGER.debug("Signaling relay: received ICE candidate")
                            on_candidate(
                                {
                                    "candidate": candidate_str,
                                    "sdpMid": data.get("sdpMid", "0"),
                                    "sdpMLineIndex": data.get("sdpMLineIndex", 0),
                                }
                            )

                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    _LOGGER.debug("Signaling relay: WS closed/error type=%s", msg.type)
                    break
            _LOGGER.debug("Signaling relay: receive loop ended")
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._closed:
                _LOGGER.exception("Signaling relay receive error")

    async def _reconnect_and_flush(self) -> None:
        """Reconnect to the signaling WebSocket to forward late browser ICE candidates.

        After the camera sends its answer and ICE candidates, the Watford server
        closes the WebSocket.  Browser ICE candidates that arrive after closure are
        buffered here and delivered via a fresh connection to the same session URL,
        allowing the camera to complete ICE negotiation.
        """
        if not self._session or not self._pending_candidates:
            return
        _LOGGER.debug(
            "Signaling relay: reconnecting to forward %d late ICE candidate(s)",
            len(self._pending_candidates),
        )
        try:
            websession = self._client._session.websession  # noqa: SLF001
            ws = await websession.ws_connect(self._session.signaling_url)
            # Swap out the list before sending so any new candidates buffered
            # during the flush are preserved for a subsequent reconnect rather
            # than being lost if we clear the list and then fail mid-send.
            pending, self._pending_candidates = self._pending_candidates, []
            sent = 0
            try:
                for msg in pending:
                    if self._closed:
                        break
                    await ws.send_json(msg)
                    sent += 1
                    _LOGGER.debug(
                        "Signaling relay: forwarded late ICE candidate via reconnect"
                    )
            finally:
                # Re-queue any candidates that were not successfully sent.
                if sent < len(pending):
                    self._pending_candidates = pending[sent:] + self._pending_candidates
                await ws.close()
        except Exception:
            if not self._closed:
                _LOGGER.debug(
                    "Signaling relay: late ICE candidate reconnect failed",
                    exc_info=True,
                )

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep the signaling connection alive."""
        try:
            while not self._closed:
                await asyncio.sleep(PING_INTERVAL)
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._closed:
                _LOGGER.debug("Relay ping loop ended")


# ---------------------------------------------------------------------------
# CameraStream — WebRTC (requires aiortc)
# ---------------------------------------------------------------------------

try:
    from aiortc import (
        RTCConfiguration,
        RTCIceServer,
        RTCPeerConnection,
        RTCSessionDescription,
    )
    from aiortc.sdp import candidate_from_sdp

    HAS_AIORTC = True
except ImportError:
    HAS_AIORTC = False


class CameraStream:
    """WebRTC live stream for an LR5 Pro camera.

    Requires the ``aiortc`` package.  Install with::

        pip install pylitterbot[camera]

    Usage::

        async with CameraStream(camera_client) as stream:
            stream.on_video_frame(my_video_handler)
            await stream.wait_for_connection()
            # ... frames delivered via callback ...
    """

    def __init__(self, client: CameraClient, **kwargs: Any) -> None:
        """Initialize the camera stream.

        Args:
            client: A ``CameraClient`` instance.
            **kwargs: Extra keyword arguments (reserved for future use).

        Raises:
            ImportError: If ``aiortc`` is not installed.

        """
        if not HAS_AIORTC:
            raise ImportError(
                "CameraStream requires the 'aiortc' package. "
                "Install it with: pip install pylitterbot[camera]"
            )

        self._client = client
        self._kwargs = kwargs

        self._session: CameraSession | None = None
        self._pc: RTCPeerConnection | None = None
        self._ws: Any | None = None  # aiohttp ClientWebSocketResponse
        self._ping_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None

        self._video_callback: Callable | None = None
        self._audio_callback: Callable | None = None
        self._state_callback: Callable | None = None

        self._connected = asyncio.Event()
        self._stopped = False

    # -- Callback registration ---------------------------------------------

    def on_video_frame(self, callback: Callable) -> None:
        """Register a callback for incoming video frames."""
        self._video_callback = callback

    def on_audio_frame(self, callback: Callable) -> None:
        """Register a callback for incoming audio frames."""
        self._audio_callback = callback

    def on_connection_state_change(self, callback: Callable) -> None:
        """Register a callback for peer connection state changes."""
        self._state_callback = callback

    # -- Lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Start the WebRTC streaming session."""
        if self._stopped:
            raise CameraStreamException("Stream has been stopped")

        # 1. Generate camera session
        self._session = await self._client.generate_session()

        # 2. Build ICE servers from TURN credentials
        ice_servers = self._build_ice_servers(self._session.turn_servers)

        # 3. Create RTCPeerConnection
        config = RTCConfiguration(iceServers=ice_servers)
        self._pc = RTCPeerConnection(configuration=config)

        # 4. Set up track handler
        @self._pc.on("track")
        def on_track(track: Any) -> None:
            _LOGGER.debug("Received %s track: %s", track.kind, track.id)
            if track.kind == "video" and self._video_callback:
                asyncio.ensure_future(self._consume_track(track, self._video_callback))
            elif track.kind == "audio" and self._audio_callback:
                asyncio.ensure_future(self._consume_track(track, self._audio_callback))

        # 5. Monitor connection state
        @self._pc.on("connectionstatechange")
        async def on_state_change() -> None:
            state = self._pc.connectionState  # type: ignore[union-attr]
            _LOGGER.debug("Connection state: %s", state)
            if state in ("connected", "completed"):
                self._connected.set()
            if self._state_callback:
                self._state_callback(state)

        # 6. Add recvonly transceivers
        self._pc.addTransceiver("video", direction="recvonly")
        self._pc.addTransceiver("audio", direction="recvonly")

        # 7. Connect to signaling websocket
        websession = self._client._session.websession
        self._ws = await websession.ws_connect(
            self._session.signaling_url,
        )

        # 8. Create and send offer
        # NOTE: setLocalDescription gathers ICE candidates internally.
        # We must send self._pc.localDescription.sdp (which includes all
        # gathered candidates) rather than offer.sdp (which has none).
        # Without our ICE candidates in the offer, the camera cannot reach
        # us and ICE connectivity checks always fail.
        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)

        local_sdp = self._pc.localDescription.sdp
        encoded_sdp = b64encode(local_sdp.encode()).decode()
        await self._ws.send_json(
            {
                "type": "offer",
                "sdp": encoded_sdp,
            }
        )

        # 9. Start receive and ping tasks
        self._receive_task = asyncio.ensure_future(self._receive_loop())
        self._ping_task = asyncio.ensure_future(self._ping_loop())

    async def stop(self) -> None:
        """Stop the WebRTC streaming session and clean up resources."""
        self._stopped = True

        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._ws.closed:
            await self._ws.close()

        if self._pc:
            await self._pc.close()

    async def wait_for_connection(self, timeout: float = 30) -> bool:
        """Wait until the WebRTC connection is established.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if connected, False if timed out.

        """
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # -- Context manager ---------------------------------------------------

    async def __aenter__(self) -> CameraStream:
        """Start the stream on context entry."""
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Stop the stream on context exit."""
        await self.stop()

    # -- Internal ----------------------------------------------------------

    @staticmethod
    def _build_ice_servers(
        turn_creds: list[dict[str, Any]],
    ) -> list[Any]:
        """Convert TURN credentials to RTCIceServer objects."""
        servers: list[RTCIceServer] = [
            RTCIceServer(urls="stun:stun.l.google.com:19302"),
        ]
        for cred in turn_creds:
            urls = cred.get("urls") or cred.get("uris") or cred.get("turnUrl") or []
            if isinstance(urls, str):
                urls = [urls]
            if urls:
                servers.append(
                    RTCIceServer(
                        urls=urls,
                        username=cred.get("username", ""),
                        credential=cred.get("credential") or cred.get("password", ""),
                    )
                )
            # Also add the STUN URL from Whisker's API format if present
            stun_url = cred.get("stunUrl")
            if stun_url and stun_url not in (s.urls for s in servers):
                servers.append(RTCIceServer(urls=stun_url))
        return servers

    async def _consume_track(self, track: Any, callback: Callable) -> None:
        """Read frames from a media track and deliver via callback."""
        try:
            while not self._stopped:
                frame = await track.recv()
                try:
                    callback(frame)
                except Exception:
                    _LOGGER.exception("Error in frame callback")
        except Exception:
            if not self._stopped:
                _LOGGER.debug("Track %s ended", track.kind)

    async def _receive_loop(self) -> None:
        """Receive messages from the signaling websocket."""
        try:
            async for msg in self._ws:  # type: ignore[union-attr]
                if self._stopped:
                    break
                if msg.type == WSMsgType.TEXT:
                    await self._handle_signaling_message(msg.json())
                elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._stopped:
                _LOGGER.exception("Signaling receive error")

    async def _handle_signaling_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming signaling message (answer or ICE candidate)."""
        msg_type = data.get("type", "")

        if msg_type == "answer":
            # SDP answer — decode from base64
            raw_sdp = data.get("payload") or data.get("sdp", "")
            try:
                sdp = b64decode(raw_sdp).decode()
            except Exception:
                sdp = raw_sdp

            answer = RTCSessionDescription(sdp=sdp, type="answer")
            await self._pc.setRemoteDescription(answer)  # type: ignore[union-attr]
            _LOGGER.debug("Set remote description (answer)")

        elif msg_type == "candidate" or "candidate" in data:
            candidate_str = data.get("candidate", "")
            if not candidate_str:
                return
            sdp_mid = data.get("sdpMid", "0")
            sdp_mline_index = data.get("sdpMLineIndex", 0)

            try:
                candidate = candidate_from_sdp(candidate_str)
                candidate.sdpMid = sdp_mid
                candidate.sdpMLineIndex = sdp_mline_index
            except Exception:
                _LOGGER.warning("Failed to parse ICE candidate: %s", candidate_str[:80])
                return

            await self._pc.addIceCandidate(candidate)  # type: ignore[union-attr]
            _LOGGER.debug("Added ICE candidate: %s", candidate_str[:60])

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep the signaling connection alive."""
        try:
            while not self._stopped:
                await asyncio.sleep(PING_INTERVAL)
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._stopped:
                _LOGGER.debug("Ping loop ended")
