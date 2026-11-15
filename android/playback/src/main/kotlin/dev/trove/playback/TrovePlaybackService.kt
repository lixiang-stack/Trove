package dev.trove.playback

import android.app.PendingIntent
import android.content.Intent
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DataSpec
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.HttpDataSource
import androidx.media3.datasource.ResolvingDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

@UnstableApi
class TrovePlaybackService : MediaSessionService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var player: ExoPlayer? = null
    private var session: MediaSession? = null
    private var positionJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        val resolver = ResolvingDataSource.Resolver { spec: DataSpec ->
            val scheme = spec.uri.scheme
            val token = PlaybackEnvironment.token
            if ((scheme == "http" || scheme == "https") && token != null) {
                spec.withRequestHeaders(mapOf("Authorization" to "Bearer $token"))
            } else {
                spec
            }
        }
        val dataSource = ResolvingDataSource.Factory(DefaultDataSource.Factory(this), resolver)
        val exoPlayer = ExoPlayer.Builder(this)
            .setMediaSourceFactory(DefaultMediaSourceFactory(dataSource))
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH)
                    .setUsage(C.USAGE_MEDIA)
                    .build(),
                true,
            )
            .setHandleAudioBecomingNoisy(true)
            .build()
        exoPlayer.addListener(progressListener)
        player = exoPlayer
        val builder = MediaSession.Builder(this, exoPlayer)
        launchIntent()?.let(builder::setSessionActivity)
        session = builder.build()
        startPositionSaver()
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? =
        session

    override fun onTaskRemoved(rootIntent: Intent?) {
        player?.let { exo ->
            if (!exo.playWhenReady || exo.mediaItemCount == 0) {
                stopSelf()
            }
        }
    }

    override fun onDestroy() {
        positionJob?.cancel()
        player?.let { exo ->
            saveProgress(
                mediaId(exo),
                exo.currentPosition,
                ended = false,
                blocking = true,
            )
        }
        session?.release()
        session = null
        player?.release()
        player = null
        scope.cancel()
        super.onDestroy()
    }

    private val progressListener = object : Player.Listener {
        override fun onIsPlayingChanged(isPlaying: Boolean) {
            if (!isPlaying) saveCurrent()
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            if (playbackState == Player.STATE_ENDED) {
                saveCurrent(ended = true)
            }
        }

        override fun onPlayerError(error: PlaybackException) {
            if (error.isUnauthorized()) {
                PlaybackEnvironment.onUnauthorized?.invoke()
            }
        }

        override fun onPositionDiscontinuity(
            oldPosition: Player.PositionInfo,
            newPosition: Player.PositionInfo,
            reason: Int,
        ) {
            if (reason == Player.DISCONTINUITY_REASON_SEEK) {
                saveCurrent()
                return
            }
            val previous = oldPosition.mediaItem?.mediaId
            if (previous != null && previous != newPosition.mediaItem?.mediaId) {
                saveProgress(previous, oldPosition.positionMs, ended = false)
            }
        }
    }

    private fun startPositionSaver() {
        positionJob = scope.launch {
            while (isActive) {
                delay(POSITION_SAVE_INTERVAL_MS)
                val exo = player ?: continue
                val itemId = mediaId(exo)
                if (exo.isPlaying && itemId.isNotBlank()) {
                    saveProgress(itemId, exo.currentPosition, ended = false)
                }
            }
        }
    }

    private fun saveCurrent(ended: Boolean = false) {
        player?.let { exo ->
            saveProgress(mediaId(exo), exo.currentPosition, ended)
        }
    }

    private fun mediaId(player: Player): String = player.currentMediaItem?.mediaId.orEmpty()

    private fun saveProgress(
        itemId: String,
        positionMs: Long,
        ended: Boolean,
        blocking: Boolean = false,
    ) {
        if (itemId.isBlank()) return
        val sink = PlaybackEnvironment.progressSink ?: return
        val block = suspend {
            sink.savePosition(itemId, positionMs.coerceAtLeast(0), ended)
        }
        if (blocking) {
            runBlocking(Dispatchers.IO) { block() }
        } else {
            scope.launch(Dispatchers.IO) { block() }
        }
    }

    private fun launchIntent(): PendingIntent? {
        val intent = packageManager.getLaunchIntentForPackage(packageName) ?: return null
        return PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private companion object {
        const val POSITION_SAVE_INTERVAL_MS = 5_000L
    }
}

private fun PlaybackException.isUnauthorized(): Boolean {
    var cause: Throwable? = this
    while (cause != null) {
        if (cause is HttpDataSource.InvalidResponseCodeException && cause.responseCode == 401) {
            return true
        }
        cause = cause.cause
    }
    return false
}
