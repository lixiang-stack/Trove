package dev.trove.playback

import kotlinx.coroutines.flow.StateFlow

data class PlaybackRequest(
    val itemId: String,
    val url: String,
    val title: String,
    val artist: String?,
    val artworkUrl: String?,
    val startPositionMs: Long = 0,
)

data class PlaybackState(
    val connected: Boolean = false,
    val itemId: String? = null,
    val title: String? = null,
    val artist: String? = null,
    val artworkUrl: String? = null,
    val isPlaying: Boolean = false,
    val isBuffering: Boolean = false,
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val speed: Float = 1f,
    val ended: Boolean = false,
    val errorCode: String? = null,
)

interface PlayerGateway {
    val state: StateFlow<PlaybackState>

    fun connect()

    fun release()

    fun play(request: PlaybackRequest)

    fun pause()

    fun toggle()

    fun seekTo(positionMs: Long)

    fun setSpeed(speed: Float)
}

interface PlaybackProgressSink {
    suspend fun savePosition(itemId: String, positionMs: Long, ended: Boolean)
}

object PlaybackEnvironment {
    @Volatile
    var token: String? = null

    @Volatile
    var progressSink: PlaybackProgressSink? = null

    @Volatile
    var onUnauthorized: (() -> Unit)? = null
}
