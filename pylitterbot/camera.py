"""Camera support for Litter-Robot 5 Pro.

Provides REST API access to camera sessions, settings, videos, and events
via `CameraClient`, and WebRTC live streaming via `CameraStream`.

WebRTC streaming requires the optional ``aiortc`` dependency::

    pip install pylitterbot[camera]
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import quote

from aiohttp import (
    ClientResponseError,
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
)

from .exceptions import CameraStreamException, InvalidCommandException
from .session import DEFAULT_USER_AGENT
from .transport import cancel_task
from .utils import decode, encode, first_value, to_timestamp, utcnow

if TYPE_CHECKING:
    from .session import Session

_LOGGER = logging.getLogger(__name__)

WATFORD_API = "https://watford.ienso-dev.com"  # vendor-maintained URL; the -dev suffix is intentional
CAMERA_SETTINGS_API = "https://7mnuil943l.execute-api.us-east-1.amazonaws.com"
CAMERA_INVENTORY_API = "https://rrntg65uwf.execute-api.us-east-1.amazonaws.com"

CAMERA_CANVAS_FRONT = "sensor_0_1080p"
CAMERA_CANVAS_GLOBE = "sensor_1_720p"

GENERATE_SESSION_PATH = "api/device-manager/client/generate-session"
SIGNALING_PATH = "api/signaling"
FALLBACK_STUN_URL = "stun:stun.l.google.com:19302"

PING_INTERVAL = 5  # seconds -- ping frequently to prevent server idle timeout (~18s)
MAX_PENDING_CANDIDATES = 50

# session.request converts HTTP 500 responses into InvalidCommandException, so
# graceful-fallback handling must catch it alongside other client errors.
_API_ERRORS = (ClientResponseError, InvalidCommandException)

_WS_HEADERS = {"User-Agent": DEFAULT_USER_AGENT}


def _decode_sdp(raw_sdp: str) -> str:
    """Return the SDP from a signaling payload that may be base64-encoded."""
    try:
        decoded = decode(raw_sdp)
        if decoded.strip().startswith("v="):
            return decoded
    except (TypeError, ValueError):
        _LOGGER.debug("Signaling: SDP not base64-encoded, using raw")
    return raw_sdp


def _is_complete_sdp(sdp: str) -> bool:
    r"""Check that an SDP answer has a version line and at least one media section.

    The camera occasionally emits a truncated answer (observed live: just
    ``"v=0\r\n"``), which hard-fails the peer's SDP parser if forwarded.
    """
    return sdp.startswith("v=") and any(
        line.startswith("m=") for line in sdp.splitlines()
    )


def _parse_signaling_message(data: dict[str, Any]) -> tuple[str, Any] | None:
    """Parse a signaling message into ``("answer", sdp)`` or ``("candidate", dict)``.

    Returns ``None`` for messages that carry neither, and for truncated
    answer SDPs (the peer would reject them; the camera may still send a
    complete answer afterwards). Explicit JSON ``null`` values for
    ``sdpMid``/``sdpMLineIndex`` are normalized to their defaults
    (``dict.get`` defaults do not apply to present-but-null keys).
    """
    msg_type = data.get("type", "")

    if msg_type == "answer":
        raw_sdp = data.get("payload") or data.get("sdp", "")
        sdp = _decode_sdp(raw_sdp)
        if not _is_complete_sdp(sdp):
            _LOGGER.warning(
                "Signaling: discarding malformed answer SDP (%d bytes): %r",
                len(sdp),
                sdp[:80],
            )
            return None
        return ("answer", sdp)

    if msg_type == "candidate" or "candidate" in data:
        if not (candidate := data.get("candidate", "")):
            return None
        sdp_mid = data.get("sdpMid")
        sdp_mline_index = data.get("sdpMLineIndex")
        return (
            "candidate",
            {
                "candidate": candidate,
                "sdpMid": "0" if sdp_mid is None else sdp_mid,
                "sdpMLineIndex": 0 if sdp_mline_index is None else sdp_mline_index,
            },
        )

    return None


@dataclass
class CameraSession:
    """Represents a camera streaming session with TURN credentials."""

    session_id: str
    session_token: str
    session_expiration: datetime | None
    signaling_url: str
    turn_servers: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def ws_url(self) -> str:
        """Return the signaling websocket URL with the URL-encoded session token."""
        return f"{self.signaling_url}?accessToken={quote(self.session_token, safe='')}"

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> CameraSession:
        """Create a CameraSession from the generate-session API response."""
        turn_creds = (
            first_value(data, ("turnServer", "turnCredentials", "iceServers")) or []
        )
        if isinstance(turn_creds, dict):
            turn_creds = [turn_creds]

        signaling_url = data.get("signalingURL", "")
        if not signaling_url:
            ws_base = WATFORD_API.replace("https://", "wss://")
            signaling_url = f"{ws_base}/{SIGNALING_PATH}"

        return cls(
            session_id=data.get("sessionId", ""),
            session_token=data.get("sessionToken", ""),
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
    created_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> VideoClip:
        """Create a VideoClip from an API response item."""
        return cls(
            id=str(data.get("id", "")),
            thumbnail_url=data.get("videoThumbnail"),
            event_type=data.get("eventType"),
            created_at=to_timestamp(data.get("createdAt")),
            raw=data,
        )


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
        self._settings_base = f"{CAMERA_SETTINGS_API}/prod/v1/cameras/{device_id}"
        self._inventory_base = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{device_id}"

    @property
    def device_id(self) -> str:
        """Return the camera device id."""
        return self._device_id

    @property
    def websession(self) -> ClientSession:
        """Return the underlying aiohttp client session."""
        return self._session.websession

    def _settings_headers(self) -> dict[str, str]:
        """Return extra headers for camera settings/inventory endpoints."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    async def _get(self, url: str, **kwargs: Any) -> Any | None:
        """GET a camera endpoint, returning ``None`` on API failure."""
        try:
            return await self._session.get(
                url, headers=self._settings_headers(), **kwargs
            )
        except _API_ERRORS as err:
            _LOGGER.debug("Camera GET %s failed: %s", url, err)
            return None

    async def _patch(self, url: str, payload: dict[str, Any]) -> bool:
        """PATCH a camera endpoint, returning ``False`` on API failure."""
        try:
            await self._session.patch(
                url, json=payload, headers=self._settings_headers()
            )
        except _API_ERRORS as err:
            _LOGGER.debug("Camera PATCH %s failed: %s", url, err)
            return False
        return True

    async def generate_session(self, *, auto_start: bool = True) -> CameraSession:
        """Create a camera streaming session.

        Returns TURN credentials and a signaling websocket URL.

        Raises:
            CameraStreamException: If the session could not be generated.

        """
        url = f"{WATFORD_API}/{GENERATE_SESSION_PATH}/{self._device_id}"
        try:
            data = await self._session.get(
                url,
                params={"autoStart": "true" if auto_start else "false"},
            )
        except _API_ERRORS as err:
            raise CameraStreamException(
                f"Failed to generate camera session for {self._device_id}: {err}"
            ) from err
        if not isinstance(data, dict):
            raise CameraStreamException(
                "Failed to generate camera session: unexpected response"
            )
        return CameraSession.from_response(data)

    async def get_video_settings(
        self, settings_type: str = "videoSettings"
    ) -> dict[str, Any] | None:
        """Fetch reported video settings for the camera.

        The endpoint wraps each settings document in a ``reportedSettings``
        list; the inner ``data`` dict for the requested type is returned.
        """
        url = f"{self._settings_base}/reported-settings/{settings_type}"
        data = await self._get(url)
        if not isinstance(data, dict):
            return None
        for item in data.get("reportedSettings", []):
            if isinstance(item, dict) and item.get("settingsType") == settings_type:
                inner = item.get("data")
                return inner if isinstance(inner, dict) else None
        return None

    async def set_camera_canvas(self, canvas: str) -> bool:
        """Set the live-view canvas (camera view selection).

        Args:
            canvas: One of ``CAMERA_CANVAS_FRONT`` or ``CAMERA_CANVAS_GLOBE``.

        """
        url = f"{self._settings_base}/desired-settings/videoSettings"
        payload = {
            "streams": {"live-view": {"canvas": canvas}},
            "timestamp": utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        return await self._patch(url, payload)

    async def set_audio_enabled(self, enabled: bool) -> bool:
        """Enable or disable the camera microphone.

        Args:
            enabled: ``True`` to unmute, ``False`` to mute.

        """
        url = f"{self._settings_base}/desired-settings/audioSettings"
        payload = {
            "audio_in": {"global": {"mute": not enabled}},
        }
        return await self._patch(url, payload)

    async def get_audio_settings(self) -> dict[str, Any] | None:
        """Fetch reported audio settings for the camera."""
        return await self.get_video_settings("audioSettings")

    async def get_camera_info(self) -> dict[str, Any] | None:
        """Fetch camera device information from the inventory API."""
        data = await self._get(self._inventory_base)
        return data if isinstance(data, dict) else None

    async def get_videos(
        self, *, date: str | None = None, limit: int | None = None
    ) -> list[VideoClip]:
        """Fetch recorded video clips.

        Args:
            date: Optional date string (YYYY-MM-DD) to filter videos.
            limit: Optional max number of results.

        """
        url = f"{self._inventory_base}/videos" + (f"/{date}" if date else "")
        params = {"limit": str(limit)} if limit is not None else None
        data = await self._get(url, params=params)
        if not isinstance(data, list):
            return []
        clips = [
            VideoClip.from_response(item) for item in data if isinstance(item, dict)
        ]
        return clips[:limit] if limit is not None else clips

    async def get_events(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Fetch camera events (AI detections, etc.).

        Args:
            limit: Optional max number of results.

        """
        url = f"{self._inventory_base}/events"
        params = {"limit": str(limit)} if limit is not None else None
        data = await self._get(url, params=params)
        if not isinstance(data, list):
            return []
        events = [item for item in data if isinstance(item, dict)]
        return events[:limit] if limit is not None else events


class _SignalingMixin:
    """Shared signaling-websocket plumbing for relay and stream classes."""

    _ws: ClientWebSocketResponse | None

    @property
    def _finished(self) -> bool:
        """Return `True` once the owner has been closed/stopped."""
        raise NotImplementedError

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep the signaling connection alive."""
        try:
            while not self._finished:
                await asyncio.sleep(PING_INTERVAL)
                if self._ws is None or self._ws.closed:
                    break
                await self._ws.ping()
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._finished:
                _LOGGER.debug("Signaling ping loop ended", exc_info=True)


class CameraSignalingRelay(_SignalingMixin):
    """Signaling relay for browser-to-camera WebRTC.

    Unlike ``CameraStream`` (which creates its own RTCPeerConnection via
    aiortc), this class only handles signaling -- forwarding SDP and ICE
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
        self._ws: ClientWebSocketResponse | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._closed = False
        self._started = False
        self._pending_candidates: list[dict[str, Any]] = []
        self._reconnect_task: asyncio.Task[None] | None = None

    @property
    def _finished(self) -> bool:
        return self._closed

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

        Raises:
            CameraStreamException: If the relay is closed/started or the
                camera session could not be generated.

        """
        if self._closed:
            raise CameraStreamException("Relay has been closed")
        if self._session is not None:
            raise CameraStreamException("Relay already started")

        self._session = await self._client.generate_session()

        try:
            websession = self._client.websession
            self._ws = await websession.ws_connect(
                self._session.ws_url, headers=_WS_HEADERS
            )

            _LOGGER.debug("Signaling relay: sending offer (%d bytes)", len(offer_sdp))
            await self._ws.send_json({"type": "offer", "sdp": encode(offer_sdp)})

            if self._pending_candidates:
                _LOGGER.debug(
                    "Signaling relay: flushing %d buffered ICE candidates",
                    len(self._pending_candidates),
                )
                for msg in self._pending_candidates:
                    await self._ws.send_json(msg)
                self._pending_candidates.clear()

            self._receive_task = asyncio.ensure_future(
                self._receive_loop(on_answer, on_candidate)
            )
            self._ping_task = asyncio.ensure_future(self._ping_loop())
            self._started = True
        except Exception:
            if self._ws is not None and not self._ws.closed:
                await self._ws.close()
            self._ws = None
            self._session = None
            raise

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
                    "Signaling relay: send failed -- buffering ICE candidate for reconnect",
                    exc_info=True,
                )

        _LOGGER.debug(
            "Signaling relay: WS closed -- buffering ICE candidate for reconnect"
        )
        if len(self._pending_candidates) >= MAX_PENDING_CANDIDATES:
            _LOGGER.warning("Signaling relay: candidate buffer full -- dropping oldest")
            self._pending_candidates.pop(0)
        self._pending_candidates.append(msg)
        # Only reconnect once start() has completed; before that, start()'s own
        # flush delivers the buffer (a parallel socket here would race the offer).
        if (
            self._started
            and not self._closed
            and (self._reconnect_task is None or self._reconnect_task.done())
        ):
            self._reconnect_task = asyncio.ensure_future(self._reconnect_and_flush())

    async def close(self) -> None:
        """Cancel tasks and close the signaling WebSocket."""
        self._closed = True

        await cancel_task(self._ping_task, self._receive_task, self._reconnect_task)

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
                if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    _LOGGER.debug("Signaling relay: WS closed/error type=%s", msg.type)
                    break
                if msg.type != WSMsgType.TEXT:
                    continue
                # isolate per-message errors so one bad frame can't end signaling
                try:
                    data = msg.json()
                    if not isinstance(data, dict):
                        continue
                    if (parsed := _parse_signaling_message(data)) is None:
                        continue
                    kind, payload = parsed
                    _LOGGER.debug("Signaling relay: received %s", kind)
                    if kind == "answer":
                        on_answer(payload)
                    else:
                        on_candidate(payload)
                except Exception:
                    _LOGGER.exception("Signaling relay: error handling message")
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

        Loops until the pending queue is empty, so candidates arriving during an
        in-flight flush are not stranded.
        """
        while self._pending_candidates and not self._closed and self._session:
            _LOGGER.debug(
                "Signaling relay: reconnecting to forward %d late ICE candidate(s)",
                len(self._pending_candidates),
            )
            try:
                websession = self._client.websession
                ws = await websession.ws_connect(
                    self._session.ws_url, headers=_WS_HEADERS
                )
                pending, self._pending_candidates = self._pending_candidates, []
                sent = 0
                try:
                    for msg in pending:
                        await ws.send_json(msg)
                        sent += 1
                        _LOGGER.debug(
                            "Signaling relay: forwarded late ICE candidate via reconnect"
                        )
                finally:
                    if sent < len(pending):
                        self._pending_candidates = (
                            pending[sent:] + self._pending_candidates
                        )
                    await ws.close()
            except Exception:
                if not self._closed:
                    _LOGGER.warning(
                        "Signaling relay: failed to forward %d late ICE candidate(s)",
                        len(self._pending_candidates),
                        exc_info=True,
                    )
                break


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


class CameraStream(_SignalingMixin):
    """WebRTC live stream for an LR5 Pro camera.

    Requires the ``aiortc`` package.  Install with::

        pip install pylitterbot[camera]

    Usage::

        async with CameraStream(camera_client) as stream:
            stream.on_video_frame(my_video_handler)
            await stream.wait_for_connection()
            # ... frames delivered via callback ...
    """

    def __init__(self, client: CameraClient) -> None:
        """Initialize the camera stream.

        Args:
            client: A ``CameraClient`` instance.

        Raises:
            ImportError: If ``aiortc`` is not installed.

        """
        if not HAS_AIORTC:
            raise ImportError(
                "CameraStream requires the 'aiortc' package. "
                "Install it with: pip install pylitterbot[camera]"
            )

        self._client = client

        self._session: CameraSession | None = None
        self._pc: RTCPeerConnection | None = None
        self._ws: ClientWebSocketResponse | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._media_tasks: list[asyncio.Task[None]] = []

        self._video_callback: Callable | None = None
        self._audio_callback: Callable | None = None
        self._state_callback: Callable | None = None

        self._connected = asyncio.Event()
        self._stopped = False

    @property
    def _finished(self) -> bool:
        return self._stopped

    def on_video_frame(self, callback: Callable) -> None:
        """Register a callback for incoming video frames."""
        self._video_callback = callback

    def on_audio_frame(self, callback: Callable) -> None:
        """Register a callback for incoming audio frames."""
        self._audio_callback = callback

    def on_connection_state_change(self, callback: Callable) -> None:
        """Register a callback for peer connection state changes."""
        self._state_callback = callback

    async def start(self) -> None:
        """Start the WebRTC streaming session.

        Raises:
            CameraStreamException: If the stream is stopped/started or the
                camera session could not be generated.

        """
        if self._stopped:
            raise CameraStreamException("Stream has been stopped")
        if self._pc is not None:
            raise CameraStreamException("Stream already started")

        self._session = await self._client.generate_session()

        ice_servers = self._build_ice_servers(self._session.turn_servers)

        config = RTCConfiguration(iceServers=ice_servers)
        self._pc = RTCPeerConnection(configuration=config)

        @self._pc.on("track")
        def on_track(track: Any) -> None:
            _LOGGER.debug("Received %s track: %s", track.kind, track.id)
            if track.kind == "video" and self._video_callback:
                task = asyncio.ensure_future(
                    self._consume_track(track, self._video_callback)
                )
                self._media_tasks.append(task)
            elif track.kind == "audio" and self._audio_callback:
                task = asyncio.ensure_future(
                    self._consume_track(track, self._audio_callback)
                )
                self._media_tasks.append(task)

        @self._pc.on("connectionstatechange")
        async def on_state_change() -> None:
            state = self._pc.connectionState  # type: ignore[union-attr]
            _LOGGER.debug("Connection state: %s", state)
            if state in ("connected", "completed"):
                self._connected.set()
            if self._state_callback:
                self._state_callback(state)

        self._pc.addTransceiver("video", direction="recvonly")
        self._pc.addTransceiver("audio", direction="recvonly")

        try:
            websession = self._client.websession
            self._ws = await websession.ws_connect(
                self._session.ws_url, headers=_WS_HEADERS
            )

            # localDescription.sdp includes gathered ICE candidates; offer.sdp has none
            offer = await self._pc.createOffer()
            await self._pc.setLocalDescription(offer)

            await self._ws.send_json(
                {
                    "type": "offer",
                    "sdp": encode(self._pc.localDescription.sdp),
                }
            )
        except Exception:
            if self._ws and not self._ws.closed:
                await self._ws.close()
            if self._pc:
                await self._pc.close()
            self._ws = None
            self._pc = None
            raise

        self._receive_task = asyncio.ensure_future(self._receive_loop())
        self._ping_task = asyncio.ensure_future(self._ping_loop())

    async def stop(self) -> None:
        """Stop the WebRTC streaming session and clean up resources."""
        self._stopped = True

        await cancel_task(*self._media_tasks, self._ping_task, self._receive_task)
        self._media_tasks.clear()

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

    async def __aenter__(self) -> CameraStream:
        """Start the stream on context entry."""
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Stop the stream on context exit."""
        await self.stop()

    @staticmethod
    def _build_ice_servers(
        turn_creds: list[dict[str, Any]],
    ) -> list[RTCIceServer]:
        """Convert TURN credentials to RTCIceServer objects.

        Prefers the vendor-provided STUN server from the session response;
        falls back to a public STUN server only if none is provided.
        """
        servers: list[RTCIceServer] = []
        has_stun = False
        for cred in turn_creds:
            urls = first_value(cred, ("turnUrl", "urls", "uris")) or []
            if isinstance(urls, str):
                urls = [urls]
            if urls:
                servers.append(
                    RTCIceServer(
                        urls=urls,
                        username=cred.get("username", ""),
                        credential=first_value(
                            cred, ("password", "credential"), default=""
                        ),
                    )
                )
            stun_url = cred.get("stunUrl")
            if stun_url and not any(
                stun_url == s.urls or (isinstance(s.urls, list) and stun_url in s.urls)
                for s in servers
            ):
                servers.append(RTCIceServer(urls=stun_url))
                has_stun = True
        if not has_stun:
            servers.append(RTCIceServer(urls=FALLBACK_STUN_URL))
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
                if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
                if msg.type != WSMsgType.TEXT:
                    continue
                # isolate per-message errors so one bad frame can't end signaling
                try:
                    data = msg.json()
                    if isinstance(data, dict):
                        await self._handle_signaling_message(data)
                except Exception:
                    if not self._stopped:
                        _LOGGER.exception("Error handling signaling message")
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._stopped:
                _LOGGER.exception("Signaling receive error")

    async def _handle_signaling_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming signaling message (answer or ICE candidate)."""
        if (parsed := _parse_signaling_message(data)) is None:
            return
        kind, payload = parsed

        if kind == "answer":
            answer = RTCSessionDescription(sdp=payload, type="answer")
            await self._pc.setRemoteDescription(answer)  # type: ignore[union-attr]
            _LOGGER.debug("Set remote description (answer)")
            return

        candidate_str = payload["candidate"]
        try:
            candidate = candidate_from_sdp(candidate_str)
            candidate.sdpMid = payload["sdpMid"]
            candidate.sdpMLineIndex = payload["sdpMLineIndex"]
            await self._pc.addIceCandidate(candidate)  # type: ignore[union-attr]
        except Exception:
            _LOGGER.warning("Failed to add ICE candidate: %s", candidate_str[:80])
            return
        _LOGGER.debug("Added ICE candidate: %s", candidate_str[:60])
