package dev.trove.app.library

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import dev.trove.app.R
import java.util.Locale

@Composable
fun processingLabel(state: String): String = when (state) {
    "completed" -> stringResource(R.string.processing_completed)
    "failed" -> stringResource(R.string.processing_failed)
    "queued" -> stringResource(R.string.processing_queued)
    "cancelled" -> stringResource(R.string.processing_cancelled)
    "downloading" -> "下载中"
    "extracting_audio" -> "抽取音频"
    "extracting_text" -> "提取文本"
    "transcribing" -> "转写中"
    "organizing" -> "整理中"
    "indexing" -> "索引中"
    else -> stringResource(R.string.processing_running)
}

@Composable
fun consumptionLabel(state: String): String = when (state) {
    "unstarted" -> stringResource(R.string.consumption_unstarted)
    "in_progress" -> stringResource(R.string.consumption_in_progress)
    "finished" -> stringResource(R.string.consumption_finished)
    else -> state
}

@Composable
fun downloadLabel(state: String): String? = when (state) {
    "completed" -> stringResource(R.string.library_download_downloaded)
    "downloading" -> stringResource(R.string.library_download_downloading)
    "queued" -> stringResource(R.string.library_download_queued)
    "failed" -> stringResource(R.string.library_download_failed)
    "paused" -> stringResource(R.string.library_download_paused)
    "partial" -> stringResource(R.string.library_download_partial)
    else -> null
}

@Composable
fun collectionDownloadLabel(state: String): String = when (state) {
    "completed" -> stringResource(R.string.library_download_downloaded)
    "downloading" -> stringResource(R.string.library_download_downloading)
    "queued" -> stringResource(R.string.library_download_queued)
    "failed" -> stringResource(R.string.library_download_failed)
    "paused" -> stringResource(R.string.library_download_paused)
    "partial" -> stringResource(R.string.library_download_partial)
    else -> stringResource(R.string.library_download_not_downloaded)
}

@Composable
fun sourceTypeLabel(value: String): String = when (value) {
    "video_url" -> stringResource(R.string.type_video)
    "podcast_episode" -> stringResource(R.string.type_podcast)
    "local_audio" -> stringResource(R.string.type_local_audio)
    "local_video" -> stringResource(R.string.type_local_video)
    "epub" -> stringResource(R.string.type_epub)
    "epub_url" -> stringResource(R.string.type_epub)
    else -> value
}

@Composable
fun platformLabel(value: String): String = when (value) {
    "youtube" -> stringResource(R.string.platform_youtube)
    "bilibili" -> stringResource(R.string.platform_bilibili)
    "podcast" -> stringResource(R.string.platform_podcast)
    "local" -> stringResource(R.string.platform_local)
    "web" -> "Web"
    else -> value
}

@Composable
fun downloadErrorLabel(item: dev.trove.core.library.LibraryItem): String? {
    val code = item.artifacts.firstNotNullOfOrNull { it.errorCode } ?: return null
    return when (code) {
        "download.quota_exceeded" -> stringResource(R.string.download_error_quota)
        "download.no_space" -> stringResource(R.string.download_error_space)
        "download.sha256_mismatch", "download.size_mismatch" ->
            stringResource(R.string.download_error_sha)

        "download.network" -> stringResource(R.string.download_error_network)
        "download.http_error" -> stringResource(R.string.download_error_http)
        "download.item_missing", "download.no_artifacts" ->
            stringResource(R.string.download_error_missing)

        else -> stringResource(R.string.download_error_generic)
    }
}

fun formatBytes(bytes: Long): String {
    if (bytes <= 0) return "0 B"
    val units = listOf("B", "KB", "MB", "GB", "TB")
    var value = bytes.toDouble()
    var unit = 0
    while (value >= 1024 && unit < units.lastIndex) {
        value /= 1024
        unit += 1
    }
    return if (unit == 0) {
        "${value.toLong()} ${units[unit]}"
    } else {
        String.format(Locale.getDefault(), "%.1f %s", value, units[unit])
    }
}
