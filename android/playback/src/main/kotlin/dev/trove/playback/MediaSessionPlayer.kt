package dev.trove.playback

import android.content.ComponentName
import android.content.Context
import android.net.Uri
import androidx.core.content.ContextCompat
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

@UnstableApi
class MediaSessionPlayer(private val context: Context) : PlayerGateway {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val _state = MutableStateFlow(PlaybackState())
    override val state: StateFlow<PlaybackState> = _state.asStateFlow()

    private var controller: MediaController? = null
    private var future: ListenableFuture<MediaController>? = null
    private var positionJob: Job? = null

    private val listener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) {
            updateFrom(player)
        }

        override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
            _state.update { it.copy(errorCode = error.errorCodeName) }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            controller?.let(::updateFrom)
        }
    }

    private val controllerListener = object : MediaController.Listener {
        override fun onDisconnected(controller: MediaController) {
            _state.update { it.copy(connected = false, isPlaying = false, isBuffering = false) }
        }
    }

    override fun connect() {
        if (controller != null || future != null) return
        val token = SessionToken(
            context,
            ComponentName(context, TrovePlaybackService::class.java),
        )
        val pending = MediaController.Builder(context, token)
            .setListener(controllerListener)
            .buildAsync()
        future = pending
        pending.addListener(
            {
                runCatching { pending.get() }
                    .onSuccess { created ->
                        controller = created
                        created.addListener(listener)
                        _state.update { it.copy(connected = true, errorCode = null) }
                        updateFrom(created)
                        startPositionUpdates()
                    }
            },
            ContextCompat.getMainExecutor(context),
        )
    }

    override fun release() {
        positionJob?.cancel()
        controller?.removeListener(listener)
        controller?.release()
        controller = null
        future?.let(MediaController::releaseFuture)
        future = null
        _state.value = PlaybackState()
    }

    override fun play(request: PlaybackRequest) {
        val active = controller ?: return
        val mediaItem = MediaItem.Builder()
            .setMediaId(request.itemId)
            .setUri(Uri.parse(request.url))
            .setMediaMetadata(
                MediaMetadata.Builder()
                    .setTitle(request.title)
                    .setArtist(request.artist)
                    .setArtworkUri(request.artworkUrl?.let(Uri::parse))
                    .build()
            )
            .build()
        active.setMediaItem(mediaItem, request.startPositionMs)
        active.prepare()
        _state.update { it.copy(errorCode = null, ended = false) }
        active.play()
    }

    override fun pause() {
        controller?.pause()
    }

    override fun toggle() {
        val active = controller ?: return
        when {
            active.playbackState == Player.STATE_ENDED -> {
                active.seekTo(0)
                active.play()
            }
            active.isPlaying -> active.pause()
            else -> active.play()
        }
    }

    override fun seekTo(positionMs: Long) {
        controller?.seekTo(positionMs.coerceAtLeast(0))
        controller?.let(::updateFrom)
    }

    override fun setSpeed(speed: Float) {
        controller?.setPlaybackSpeed(speed)
        controller?.let(::updateFrom)
    }

    private fun startPositionUpdates() {
        if (positionJob != null) return
        positionJob = scope.launch {
            while (isActive) {
                controller?.let(::updateFrom)
                delay(POSITION_TICK_MS)
            }
        }
    }

    private fun updateFrom(player: Player) {
        val mediaItem = player.currentMediaItem
        val metadata = mediaItem?.mediaMetadata
        _state.update {
            PlaybackState(
                connected = true,
                itemId = mediaItem?.mediaId,
                title = metadata?.title?.toString(),
                artist = metadata?.artist?.toString(),
                artworkUrl = metadata?.artworkUri?.toString(),
                isPlaying = player.isPlaying,
                isBuffering = player.playbackState == Player.STATE_BUFFERING,
                positionMs = player.currentPosition.coerceAtLeast(0),
                durationMs = player.duration.takeIf { duration ->
                    duration > 0 && duration != C.TIME_UNSET
                } ?: 0,
                speed = player.playbackParameters.speed,
                ended = player.playbackState == Player.STATE_ENDED,
                errorCode = it.errorCode,
            )
        }
    }

    private companion object {
        const val POSITION_TICK_MS = 1_000L
    }
}
