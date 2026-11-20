"""Camera support for Litter-Robot 5 Pro.

Provides REST API access to camera sessions, settings, videos (including
direct MP4 download of recorded clips), and events via `CameraClient`, and
WebRTC live streaming via `CameraStream`.

WebRTC streaming requires the optional ``aiortc`` dependency::

    pip install pylitterbot[camera]
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date as _date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, TypeVar
from urllib.parse import quote

from aiohttp import (
    ClientError,
    ClientResponseError,
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
)
from yarl import URL

from .exceptions import CameraStreamException, InvalidCommandException
from .session import DEFAULT_USER_AGENT
from .transport import cancel_task
from .utils import decode, encode, first_value, to_timestamp, utcnow

if TYPE_CHECKING:
    from .session import Session

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")

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
# The camera may ignore an offer entirely, so retry it on a fresh session.
ANSWER_TIMEOUT = 10  # seconds
ANSWER_ATTEMPTS = 2
# aiohttp waits up to 10s for the server's close frame; cleanup should not
WS_CLOSE_TIMEOUT = 2  # seconds
# late ICE candidates: retries after a failed reconnect, with linear backoff
RECONNECT_ATTEMPTS = 3
RECONNECT_BACKOFF = 0.5  # seconds

# session.request converts HTTP 500 responses into InvalidCommandException, so
# graceful-fallback handling must catch it alongside other client errors.
_API_ERRORS = (ClientResponseError, InvalidCommandException)

# Upper bound on pages fetched by ``CameraClient.get_videos`` (the API returns
# 10 clips per page, and keeps 2 days of clips, or 30 with Whisker+).
MAX_VIDEO_PAGES = 50


# "Area/Location" IANA names, e.g. "America/Denver" or "Etc/GMT-10", plus bare
# "UTC" (a common TZ override, e.g. in containers). Checked by
# syntax alone: loading the zone would read tzdata from disk, which blocks the
# event loop. POSIX TZ strings such as "AEST-10" or "EST5EDT,M3.2.0,M11.1.0"
# don't match.
_IANA_TIMEZONE = re.compile(r"UTC|[A-Za-z][\w+-]*(?:/[\w+-]+)+")


def local_timezone_name() -> str:
    """Return this system's IANA timezone name, falling back to ``"UTC"``.

    Checks the ``TZ`` environment variable, then the ``/etc/localtime``
    symlink (Linux and macOS).  Names are checked by syntax only, so this
    doesn't read tzdata and is safe to call in the event loop.  Pass a
    timezone explicitly where one is configured (e.g. Home Assistant's
    ``hass.config.time_zone``).
    """
    if (tz := os.environ.get("TZ", "").lstrip(":")) and _IANA_TIMEZONE.fullmatch(tz):
        return tz
    try:
        target = os.path.realpath("/etc/localtime")
    except OSError:
        target = ""
    if "zoneinfo/" in target:
        name = target.split("zoneinfo/", 1)[1]
        if _IANA_TIMEZONE.fullmatch(name):
            return name
    return "UTC"


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


def _append_bounded(buffer: list[dict[str, Any]], msg: dict[str, Any]) -> None:
    """Append an ICE candidate message, dropping the oldest when full."""
    if len(buffer) >= MAX_PENDING_CANDIDATES:
        _LOGGER.warning("Signaling relay: candidate buffer full -- dropping oldest")
        buffer.pop(0)
    buffer.append(msg)


async def _close_ws(ws: ClientWebSocketResponse) -> None:
    """Close a websocket, aborting the connection after ``WS_CLOSE_TIMEOUT``.

    Cancelling aiohttp's close (as the timeout does) releases the underlying
    connection instead of waiting for the server's close frame.
    """
    try:
        # asyncio.wait_for can swallow a cancellation on 3.11
        async with asyncio.timeout(WS_CLOSE_TIMEOUT):
            await ws.close()
    except asyncio.TimeoutError:
        _LOGGER.debug("Signaling: websocket close timed out; connection aborted")


async def _cancel_and_wait(*tasks: asyncio.Task[Any] | None) -> None:
    """Cancel tasks and wait for their cleanup to finish.

    Unlike ``cancel_task``, a cancellation of the caller still propagates, and
    it doesn't interrupt the tasks' own cleanup.
    """
    pending = {task for task in tasks if task is not None and not task.done()}
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.wait(pending)


async def _finish_before_cancelling(coro: Coroutine[Any, Any, _T]) -> _T:
    """Await ``coro``; if the caller is cancelled, let it finish first.

    The cancellation is raised once ``coro`` is done, even if further
    cancellations (e.g. from overlapping stop() calls) arrive meanwhile.
    """
    task = asyncio.ensure_future(coro)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                pass
        raise


async def _wait_for_either(first: asyncio.Event, second: asyncio.Event) -> None:
    """Wait until either event is set."""
    waiters = {
        asyncio.ensure_future(first.wait()),
        asyncio.ensure_future(second.wait()),
    }
    try:
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)


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

    @property
    def is_expired(self) -> bool:
        """Return `True` once the session is past its ``sessionExpiration``.

        Sessions last about 60 seconds. The signaling server may still accept
        an expired token, so this does not mean the session is unusable.
        """
        return (
            self.session_expiration is not None and utcnow() >= self.session_expiration
        )

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


@dataclass
class VideoPlayback:
    """Signed playback details for a recorded video clip.

    The ``hls_url`` on a :class:`VideoClip` is unsigned and is rejected by the
    CDN with HTTP 403.  :meth:`CameraClient.get_video_playback` exchanges a clip
    id for short-lived CloudFront signed cookies; send them (see
    :attr:`cookie_header`) when fetching the HLS playlist and its segments.
    """

    clip_id: str
    hls_url: str | None
    cookies: dict[str, str]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def cookie_header(self) -> str:
        """Return the cookies formatted as an HTTP ``Cookie`` header value."""
        return "; ".join(f"{name}={value}" for name, value in self.cookies.items())

    @property
    def chunks(self) -> list[VideoChunk]:
        """Return the clip's MP4 chunks, in playback order.

        These are the same segments the HLS playlist references, but exposed
        as presigned S3 URLs that need no cookies or auth headers.
        """
        chunks = self.raw.get("chunks")
        if not isinstance(chunks, list):
            return []
        return [
            VideoChunk(id=str(chunk.get("id", "")), download_url=url)
            for chunk in chunks
            if isinstance(chunk, dict)
            and isinstance(url := chunk.get("downloadUrl"), str)
            and url
        ]


@dataclass
class VideoChunk:
    """One MP4 chunk of a recorded clip.

    ``download_url`` is a presigned S3 URL that expires roughly 15 minutes after
    :meth:`CameraClient.get_video_playback` is called, so download promptly.
    """

    id: str
    download_url: str


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

    async def validate_device_ownership(self) -> bool:
        """Check that the account owns this camera.

        The Whisker app makes this call immediately before generating a live
        view session. A successful response has an empty body.

        Returns:
            ``True`` if the account owns the camera, ``False`` if the API
            refuses it (HTTP 401 or 403).

        Raises:
            aiohttp.ClientResponseError: For any other HTTP error (e.g. 429),
                so a failed check isn't mistaken for "not your camera".
            InvalidCommandException: If the API returns HTTP 500.
            aiohttp.ClientError: If the request couldn't be made.

        """
        url = f"{CAMERA_INVENTORY_API}/prod/v1/auth/validate-token"
        payload = {
            "device_id": self._device_id,
            "validation_type": "device_ownership",
        }
        try:
            await self._session.post(
                url, json=payload, headers=self._settings_headers()
            )
        except ClientResponseError as err:
            # the empty body can't be decoded as JSON unless the response is
            # labelled application/json (ContentTypeError carries the 2xx)
            if 200 <= err.status < 300:
                return True
            if err.status not in (401, 403):
                raise
            _LOGGER.debug("Camera ownership validation refused: %s", err)
            return False
        return True

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
        items = data.get("reportedSettings")
        if not isinstance(items, list):
            return None
        for item in items:
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

    async def get_camera_canvas(self) -> str | None:
        """Return the reported live-view canvas (camera view selection)."""
        settings = await self.get_video_settings()
        if not settings:
            return None
        streams = settings.get("streams")
        live_view = streams.get("live-view") if isinstance(streams, dict) else None
        canvas = live_view.get("canvas") if isinstance(live_view, dict) else None
        return canvas if isinstance(canvas, str) else None

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

    async def get_camera_status(self) -> str | None:
        """Return the camera's connection status from the inventory API.

        The Whisker app polls this before offering live view; ``"ONLINE"``
        indicates the camera can accept a streaming session.
        """
        info = await self.get_camera_info()
        status = info.get("status") if info else None
        return status if isinstance(status, str) else None

    async def get_videos(
        self,
        *,
        date: str | _date | None = None,
        limit: int | None = None,
        timezone: str | None = None,
        max_pages: int = MAX_VIDEO_PAGES,
    ) -> list[VideoClip]:
        """Fetch recorded video clips, newest first.

        The API returns clips 10 per page; pages are fetched one after another
        until one comes back empty (or repeats clips already seen), ``limit``
        is reached, or ``max_pages`` have been read.  This can take many
        requests, so avoid calling it on a polling interval.

        If a later page fails (an API or connection error, or a timeout),
        paging stops and the clips gathered so far are returned (the error is
        logged at debug level).  A connection error or timeout on the first
        page is raised.

        The ``timezone`` sent matters: the API does not reliably return the
        most recent clips unless it is given the account's local timezone
        (as the Whisker app does), and ``date`` is interpreted as a day in
        that timezone.

        Args:
            date: Optional day to filter videos, as a :class:`datetime.date` or
                a ``YYYY-MM-DD`` string, read in ``timezone``.  A
                :class:`~datetime.datetime` is rejected, since its time
                would be ignored.
            limit: Optional max number of results, applied client-side.
            timezone: IANA timezone name (e.g. ``"Australia/Sydney"``).
                Defaults to :func:`local_timezone_name`.
            max_pages: Safety cap on the number of pages requested.

        """
        if isinstance(date, datetime):
            raise TypeError("date must be a datetime.date or string, not a datetime")
        if isinstance(date, _date):
            date = date.isoformat()
        url = f"{self._inventory_base}/videos" + (f"/{date}" if date else "")
        tz = timezone or local_timezone_name()
        clips: list[VideoClip] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            try:
                data = await self._get(url, params={"page": str(page), "timezone": tz})
            except (ClientError, asyncio.TimeoutError) as err:
                if page == 1:
                    raise
                _LOGGER.debug("Camera video page %d failed: %s", page, err)
                break
            if not isinstance(data, list):
                break
            added = 0
            for item in data:
                if not isinstance(item, dict):
                    continue
                clip = VideoClip.from_response(item)
                if clip.id in seen:  # duplicate within or across pages
                    continue
                seen.add(clip.id)
                clips.append(clip)
                added += 1
            if not added:
                break
            if limit is not None and len(clips) >= limit:
                break
        return clips[:limit] if limit is not None else clips

    async def get_video_playback(self, clip_id: str) -> VideoPlayback | None:
        """Fetch signed playback details for a recorded clip.

        The clip's ``hlsUrl`` (from :meth:`get_videos`) is unsigned and is
        rejected by the CDN with HTTP 403.  The clip-detail endpoint responds
        with the CloudFront signed cookies (``CloudFront-Policy``,
        ``CloudFront-Signature`` and ``CloudFront-Key-Pair-Id``) required to
        stream it; pass them as a ``Cookie`` header when fetching the ``.m3u8``
        playlist and its segments.

        Args:
            clip_id: The :attr:`VideoClip.id` of the clip to play.

        Returns:
            A :class:`VideoPlayback`, or ``None`` on API failure. The cookies
            are short-lived, so fetch and use them promptly.

        """
        # The detail endpoint lives under ``camera-videos`` (not the per-device
        # ``cameras/{id}/videos`` listing) and sets the CloudFront cookies as
        # response headers, so it must be read from the raw session rather than
        # the JSON-only ``_get`` helper.
        url = f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{quote(str(clip_id))}"
        headers = self._settings_headers()
        if (auth := await self._session.get_bearer_authorization()) is not None:
            headers["authorization"] = auth
        try:
            async with self.websession.get(url, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                cookies = {
                    name: morsel.value
                    for name, morsel in resp.cookies.items()
                    if name.startswith("CloudFront-")
                }
        except _API_ERRORS as err:
            _LOGGER.debug("Camera video playback %s failed: %s", clip_id, err)
            return None
        if not isinstance(data, dict):
            return None
        return VideoPlayback(
            clip_id=str(clip_id),
            hls_url=data.get("hlsUrl"),
            cookies=cookies,
            raw=data,
        )

    async def fetch_video_chunks(self, clip_id: str) -> list[bytes] | None:
        """Download a recorded clip's MP4 chunks directly from S3.

        Uses the presigned ``chunks[].downloadUrl`` values from the clip-detail
        endpoint rather than the CloudFront HLS stream, so no cookies or
        playlist parsing are needed.  Chunks are separate MP4 files in playback
        order; concatenate them (e.g. ``ffmpeg -f concat -c copy``) for a
        single file.

        Args:
            clip_id: The :attr:`VideoClip.id` of the clip to download.

        Returns:
            The chunk contents in playback order, an empty list if the clip has
            no chunks yet, or ``None`` if the clip details could not be fetched.

        Raises:
            aiohttp.ClientError: If any chunk download fails (an HTTP error
                status or a connection error).  Nothing is returned for a
                partially downloaded clip.
            asyncio.TimeoutError: If a chunk download times out.

        """
        if (playback := await self.get_video_playback(clip_id)) is None:
            return None
        contents: list[bytes] = []
        for chunk in playback.chunks:
            # Presigned S3 URL: pylitterbot adds its auth per request, so none is
            # sent here (S3 rejects a second auth mechanism), and the session's
            # cookies stay scoped to the domains that set them.  Keep the query
            # string exactly as signed.
            async with self.websession.get(
                URL(chunk.download_url, encoded=True)
            ) as resp:
                resp.raise_for_status()
                contents.append(await resp.read())
        return contents

    async def download_video(
        self, clip_id: str, directory: str | Path
    ) -> list[Path] | None:
        """Download a recorded clip's MP4 chunks to ``directory``.

        Files are named ``{clip_id}_{index:02d}.mp4`` in playback order, and
        existing files with those names are overwritten.  All chunks are
        fetched before anything is written, so a failed download leaves no
        partial files behind.  The directory is created if needed.

        Args:
            clip_id: The :attr:`VideoClip.id` of the clip to download.
            directory: Where to write the chunk files.

        Returns:
            The written file paths in playback order, an empty list if the clip
            has no chunks yet, or ``None`` if the clip details could not be
            fetched.

        Raises:
            ValueError: If ``clip_id`` isn't a plain file name (e.g. contains
                a path separator), so files can't land outside ``directory``.
            aiohttp.ClientError: If any chunk download fails (an HTTP error
                status or a connection error).
            asyncio.TimeoutError: If a chunk download times out.

        """
        if not clip_id or Path(clip_id).name != clip_id:
            raise ValueError(f"Invalid clip ID for a file name: {clip_id!r}")
        if (contents := await self.fetch_video_chunks(clip_id)) is None:
            return None
        directory = Path(directory)
        paths = [
            directory / f"{clip_id}_{index:02d}.mp4" for index in range(len(contents))
        ]

        def _write() -> None:
            directory.mkdir(parents=True, exist_ok=True)
            for path, data in zip(paths, contents):
                path.write_bytes(data)

        if contents:
            await asyncio.to_thread(_write)
        return paths

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
    _setup_task: asyncio.Task[Any] | None

    @property
    def _finished(self) -> bool:
        """Return `True` once the owner has been closed/stopped."""
        raise NotImplementedError

    async def _run_setup(
        self, setup: Coroutine[Any, Any, _T], finished_message: str
    ) -> _T:
        """Run offer setup as a task that close()/stop() can cancel and wait for.

        Cancelling it lets its own cleanup release a socket that isn't yet
        tracked, so no setup socket outlives close()/stop().
        """
        self._setup_task = task = asyncio.ensure_future(setup)
        try:
            return await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if (
                task.cancelled()
                and self._finished
                and not (current and current.cancelling())
            ):
                # cancelled by close()/stop(), not by our caller
                raise CameraStreamException(finished_message) from None
            raise
        finally:
            self._setup_task = None

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
        self._closed_event = asyncio.Event()  # wakes start() on close()
        self._setup_task: asyncio.Task[CameraSession] | None = None
        self._starting = False
        self._started = False  # set once the camera has answered
        self._offer_candidates: list[dict[str, Any]] = []
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
        """Send the offer and wait for the camera's answer.

        The answer and the camera's ICE candidates are delivered through the
        callbacks; ICE candidates may continue to arrive after this returns.
        If the camera does not answer within ``ANSWER_TIMEOUT`` seconds, the
        offer is retried on a fresh session, up to ``ANSWER_ATTEMPTS`` times.
        This usually returns in 1-3 seconds, but can take about 25 seconds
        before raising.

        If ``start()`` raises (other than because the relay was closed), it
        can be called again with a new offer to retry.

        Args:
            offer_sdp: The browser's SDP offer (plain text, not base64).
            on_answer: Called with the decoded SDP answer from the camera.
            on_candidate: Called with ICE candidate dicts from the camera.

        Returns:
            The ``CameraSession`` with TURN credentials.

        Raises:
            CameraStreamException: If the relay is closed/started, the camera
                session could not be generated, or the camera never answered.

        """
        if self._closed:
            raise CameraStreamException("Relay has been closed")
        # _session is only set once setup has awaited, so it can't guard alone
        if self._starting or self._session is not None:
            raise CameraStreamException("Relay already started")
        self._starting = True

        current_attempt = 0

        def _attempt_handlers(
            attempt: int, answered: asyncio.Event
        ) -> tuple[Callable[[str], None], Callable[[dict[str, Any]], None]]:
            """Return callbacks that only act while ``attempt`` is current."""

            def _on_answer(sdp: str) -> None:
                if attempt != current_attempt:
                    _LOGGER.debug(
                        "Signaling relay: ignoring answer from abandoned attempt %d",
                        attempt,
                    )
                    return
                self._started = True
                answered.set()
                on_answer(sdp)

            def _on_candidate(candidate: dict[str, Any]) -> None:
                if attempt == current_attempt:
                    on_candidate(candidate)

            return _on_answer, _on_candidate

        try:
            for attempt in range(1, ANSWER_ATTEMPTS + 1):
                current_attempt = attempt
                answered = asyncio.Event()
                session = await self._run_setup(
                    self._connect_and_offer(
                        offer_sdp, *_attempt_handlers(attempt, answered)
                    ),
                    "Relay has been closed",
                )
                try:
                    # asyncio.wait_for can swallow a cancellation on 3.11
                    async with asyncio.timeout(ANSWER_TIMEOUT):
                        await _wait_for_either(answered, self._closed_event)
                except asyncio.TimeoutError:
                    pass
                if self._closed:
                    raise CameraStreamException("Relay has been closed")
                if answered.is_set():
                    # may have landed as the deadline passed; already forwarded
                    self._schedule_flush()
                    return session
                # invalidate before _disconnect() yields to the receive loop
                current_attempt = 0
                # the next attempt replays these with its offer
                self._pending_candidates.clear()
                _LOGGER.warning(
                    "Signaling relay: camera did not answer within %ss (attempt %d of %d)",
                    ANSWER_TIMEOUT,
                    attempt,
                    ANSWER_ATTEMPTS,
                )
                await self._disconnect()
                if self._closed:
                    raise CameraStreamException("Relay has been closed")
            raise CameraStreamException(
                f"Camera {self._client.device_id} did not answer the offer "
                f"after {ANSWER_ATTEMPTS} attempts"
            )
        except BaseException:
            await self._disconnect()
            self._session = None
            self._started = False
            # a later start() is a new offer; don't replay this one's candidates
            self._offer_candidates.clear()
            self._pending_candidates.clear()
            raise
        finally:
            self._starting = False

    async def _connect_and_offer(
        self,
        offer_sdp: str,
        on_answer: Callable[[str], None],
        on_candidate: Callable[[dict[str, Any]], None],
    ) -> CameraSession:
        """Open a fresh session and send the offer plus early ICE candidates."""
        self._session = session = await self._client.generate_session()
        ws = await self._client.websession.ws_connect(
            session.ws_url, headers=_WS_HEADERS
        )
        try:
            _LOGGER.debug("Signaling relay: sending offer (%d bytes)", len(offer_sdp))
            await ws.send_json({"type": "offer", "sdp": encode(offer_sdp)})
        except BaseException:
            # not yet in self._ws, so start()'s cleanup can't close it
            await _close_ws(ws)
            raise

        # Publish the socket and snapshot the early candidates with no await in
        # between, so each is sent exactly once and only after the offer.
        self._ws = ws
        early = list(self._offer_candidates)
        if early:
            _LOGGER.debug(
                "Signaling relay: sending %d early ICE candidate(s)", len(early)
            )
        for index, msg in enumerate(early):
            try:
                await ws.send_json(msg)
            except Exception:
                # the server closes the socket right after answering, so keep
                # receiving; start() flushes the rest once answered, or the
                # next attempt replays them
                _LOGGER.debug(
                    "Signaling relay: early ICE candidate send failed", exc_info=True
                )
                for unsent in early[index:]:
                    _append_bounded(self._pending_candidates, unsent)
                break

        self._receive_task = asyncio.ensure_future(
            self._receive_loop(on_answer, on_candidate)
        )
        self._ping_task = asyncio.ensure_future(self._ping_loop())
        return session

    async def _disconnect(self) -> None:
        """Stop the signaling tasks and close the websocket."""
        await cancel_task(self._ping_task, self._receive_task)
        self._ping_task = self._receive_task = None
        if self._ws is not None and not self._ws.closed:
            await _close_ws(self._ws)
        self._ws = None

    async def send_candidate(self, candidate: dict[str, Any]) -> None:
        """Forward a browser ICE candidate to the camera.

        Until the camera answers, candidates are kept and sent with each offer
        attempt. After that, candidates that arrive once the signaling
        WebSocket has closed are delivered over a fresh connection.

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
        if not self._started:
            _append_bounded(self._offer_candidates, msg)
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_json(msg)
                return
            except Exception:
                _LOGGER.debug(
                    "Signaling relay: send failed -- buffering ICE candidate",
                    exc_info=True,
                )
                if not self._started:
                    # the socket may already hold the answer (the server closes
                    # it right after), so start() flushes this once answered
                    _append_bounded(self._pending_candidates, msg)
                    return
        if not self._started:
            # the next offer attempt sends it
            return

        _LOGGER.debug(
            "Signaling relay: WS closed -- buffering ICE candidate for reconnect"
        )
        _append_bounded(self._pending_candidates, msg)
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        """Deliver pending ICE candidates over a fresh connection.

        Only once the camera has answered; before that, each offer attempt
        sends the early candidates (a parallel socket would race it).
        """
        if (
            self._pending_candidates
            and self._started
            and not self._closed
            and (self._reconnect_task is None or self._reconnect_task.done())
        ):
            self._reconnect_task = asyncio.ensure_future(self._reconnect_and_flush())

    async def close(self) -> None:
        """Cancel tasks and close the signaling WebSocket."""
        self._closed = True
        self._closed_event.set()

        # an in-flight offer setup closes its own socket when cancelled
        await _cancel_and_wait(self._setup_task, self._reconnect_task)
        await self._disconnect()

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
        in-flight flush are not stranded. A failed reconnect or send is retried
        up to ``RECONNECT_ATTEMPTS`` times, resending only unsent candidates.
        """
        failures = 0
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
                        # unsent ones first, then new arrivals; keep the newest
                        self._pending_candidates = (
                            pending[sent:] + self._pending_candidates
                        )[-MAX_PENDING_CANDIDATES:]
                    await _close_ws(ws)
            except Exception:
                # close() cancels this task, so a closed relay never sleeps here
                failures += 1
                if failures >= RECONNECT_ATTEMPTS:
                    _LOGGER.warning(
                        "Signaling relay: failed to forward %d late ICE candidate(s)",
                        len(self._pending_candidates),
                        exc_info=True,
                    )
                    break
                _LOGGER.debug(
                    "Signaling relay: reconnect failed, retrying", exc_info=True
                )
                await asyncio.sleep(RECONNECT_BACKOFF * failures)


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
        self._tracks: dict[str, Any] = {}
        self._consuming: set[str] = set()

        self._video_callback: Callable | None = None
        self._audio_callback: Callable | None = None
        self._state_callback: Callable | None = None

        self._answered = asyncio.Event()
        self._connected = asyncio.Event()
        self._starting = False
        self._stopped = False
        self._stopped_event = asyncio.Event()  # wakes start() on stop()
        self._setup_task: asyncio.Task[None] | None = None
        self._teardown_task: asyncio.Task[None] | None = None

    @property
    def _finished(self) -> bool:
        return self._stopped

    def on_video_frame(self, callback: Callable) -> None:
        """Register a callback for incoming video frames."""
        self._video_callback = callback
        self._start_consumer("video")

    def on_audio_frame(self, callback: Callable) -> None:
        """Register a callback for incoming audio frames."""
        self._audio_callback = callback
        self._start_consumer("audio")

    def on_connection_state_change(self, callback: Callable) -> None:
        """Register a callback for peer connection state changes."""
        self._state_callback = callback

    async def start(self) -> None:
        """Start the WebRTC streaming session and wait for the camera's answer.

        If the camera does not answer within ``ANSWER_TIMEOUT`` seconds, the
        offer is retried on a fresh session, up to ``ANSWER_ATTEMPTS`` times.

        If ``start()`` raises (other than because the stream was stopped), it
        can be called again to retry.

        Raises:
            CameraStreamException: If the stream is stopped/started, the
                camera session could not be generated, or the camera never
                answered.

        """
        if self._stopped:
            raise CameraStreamException("Stream has been stopped")
        # _pc is cleared between attempts, so it can't serve as the guard alone
        if self._starting or self._pc is not None:
            raise CameraStreamException("Stream already started")

        self._starting = True
        try:
            # a cancelled earlier start() can leave its teardown running, which
            # would clear this attempt's socket and tasks
            await self._join_teardown()
            self._check_stopped()
            for attempt in range(1, ANSWER_ATTEMPTS + 1):
                self._answered = asyncio.Event()
                self._connected.clear()
                await self._run_setup(
                    self._connect_and_offer(), "Stream has been stopped"
                )
                self._check_stopped()
                try:
                    # asyncio.wait_for can swallow a cancellation on 3.11
                    async with asyncio.timeout(ANSWER_TIMEOUT):
                        await _wait_for_either(self._answered, self._stopped_event)
                except asyncio.TimeoutError:
                    pass
                self._check_stopped()
                if self._answered.is_set():
                    # may have landed as the deadline passed
                    return
                _LOGGER.warning(
                    "Camera did not answer within %ss (attempt %d of %d)",
                    ANSWER_TIMEOUT,
                    attempt,
                    ANSWER_ATTEMPTS,
                )
                await self._disconnect()
                self._check_stopped()
            raise CameraStreamException(
                f"Camera {self._client.device_id} did not answer the offer "
                f"after {ANSWER_ATTEMPTS} attempts"
            )
        except BaseException:
            await self._disconnect()
            raise
        finally:
            self._starting = False

    def _check_stopped(self) -> None:
        """Raise if stop() was called, e.g. while start() was awaiting."""
        if self._stopped:
            raise CameraStreamException("Stream has been stopped")

    async def _connect_and_offer(self) -> None:
        """Open a fresh session and peer connection, then send the offer.

        stop() can run at any await here and release the connection, so
        each await is followed by a stopped check.
        """
        self._session = await self._client.generate_session()
        self._check_stopped()

        ice_servers = self._build_ice_servers(self._session.turn_servers)

        config = RTCConfiguration(iceServers=ice_servers)
        self._pc = pc = RTCPeerConnection(configuration=config)

        # Events from a peer that teardown has detached (a timed-out attempt,
        # or a stopped stream) must not reach the current one.
        @pc.on("track")
        def on_track(track: Any) -> None:
            if pc is not self._pc:
                return
            _LOGGER.debug("Received %s track: %s", track.kind, track.id)
            self._tracks[track.kind] = track
            self._start_consumer(track.kind)

        @pc.on("connectionstatechange")
        async def on_state_change() -> None:
            state = pc.connectionState
            _LOGGER.debug("Connection state: %s", state)
            if pc is self._pc:
                if state in ("connected", "completed"):
                    self._connected.set()
            elif not self._stopped:
                return  # a retry's abandoned peer
            if self._state_callback:
                self._state_callback(state)

        pc.addTransceiver("video", direction="recvonly")
        pc.addTransceiver("audio", direction="recvonly")

        websession = self._client.websession
        self._ws = ws = await websession.ws_connect(
            self._session.ws_url, headers=_WS_HEADERS
        )
        self._check_stopped()

        # localDescription.sdp includes gathered ICE candidates; offer.sdp has none
        offer = await pc.createOffer()
        self._check_stopped()
        # Interrupting ICE gathering orphans aioice's TURN allocation task, so
        # an allocation that then succeeds leaks its socket; aioice gives up on
        # gathering after 5 seconds, so let it finish
        await _finish_before_cancelling(pc.setLocalDescription(offer))
        self._check_stopped()

        await ws.send_json(
            {
                "type": "offer",
                "sdp": encode(pc.localDescription.sdp),
            }
        )
        self._check_stopped()

        self._receive_task = asyncio.ensure_future(self._receive_loop())
        self._ping_task = asyncio.ensure_future(self._ping_loop())

    async def _disconnect(self) -> None:
        """Stop the media and signaling tasks and close the connections.

        Teardown runs as an owned task, so a cancelled caller can't interrupt
        it. An overlapping call (e.g. stop() during a retry's teardown) waits
        for the one in progress: by then the peer is detached and the socket
        marked closed, so it would otherwise find nothing left and return early.
        """
        await self._join_teardown()
        self._teardown_task = task = asyncio.ensure_future(self._teardown())
        await asyncio.wait({task})

    async def _join_teardown(self) -> None:
        """Wait for a teardown in progress, if any."""
        while (task := self._teardown_task) is not None and not task.done():
            await asyncio.wait({task})

    async def _teardown(self) -> None:
        """Release the peer, socket and tasks; run only via ``_disconnect``."""
        # detach the peer first, so its events are ignored while we await
        pc, self._pc = self._pc, None
        try:
            await cancel_task(*self._media_tasks, self._ping_task, self._receive_task)
            self._media_tasks.clear()
            self._tracks.clear()
            self._consuming.clear()
            self._ping_task = self._receive_task = None

            if self._ws and not self._ws.closed:
                await _close_ws(self._ws)
            self._ws = None
        finally:
            if pc:
                await pc.close()

    async def stop(self) -> None:
        """Stop the WebRTC streaming session and clean up resources.

        If ``start()`` is gathering ICE candidates, this waits for gathering
        to finish (at most about 5 seconds) so no TURN socket is left open.
        """
        self._stopped = True
        self._stopped_event.set()
        # setup closes a socket it hasn't published yet when cancelled
        await _cancel_and_wait(self._setup_task)
        await self._disconnect()

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

    def _frame_callback(self, kind: str) -> Callable | None:
        """Return the registered callback for a track kind."""
        if kind == "video":
            return self._video_callback
        if kind == "audio":
            return self._audio_callback
        return None

    def _start_consumer(self, kind: str) -> None:
        """Consume a track once both it and its callback exist.

        Tracks arrive while ``start()`` is waiting for the answer, so a
        callback registered after ``start()`` must still pick them up.
        """
        track = self._tracks.get(kind)
        if track is None or self._frame_callback(kind) is None:
            return
        if kind in self._consuming:
            return
        self._consuming.add(kind)
        self._media_tasks.append(asyncio.ensure_future(self._consume_track(track)))

    async def _consume_track(self, track: Any) -> None:
        """Read frames from a media track and deliver via callback."""
        try:
            while not self._stopped:
                frame = await track.recv()
                if (callback := self._frame_callback(track.kind)) is None:
                    continue
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
        if (pc := self._pc) is None:
            return  # detached by teardown
        kind, payload = parsed

        if kind == "answer":
            answer = RTCSessionDescription(sdp=payload, type="answer")
            await pc.setRemoteDescription(answer)
            _LOGGER.debug("Set remote description (answer)")
            if pc is self._pc:
                self._answered.set()
            return

        candidate_str = payload["candidate"]
        try:
            candidate = candidate_from_sdp(candidate_str)
            candidate.sdpMid = payload["sdpMid"]
            candidate.sdpMLineIndex = payload["sdpMLineIndex"]
            await pc.addIceCandidate(candidate)
        except Exception:
            _LOGGER.warning("Failed to add ICE candidate: %s", candidate_str[:80])
            return
        _LOGGER.debug("Added ICE candidate: %s", candidate_str[:60])
