package dev.trove.core.storage

import java.io.File

private val SAFE_SEGMENT = Regex("[^A-Za-z0-9._-]")

class ArtifactFileStore(private val root: File) {
    init {
        require(root.isDirectory || root.mkdirs() || root.isDirectory) {
            "Cannot create artifact directory: $root"
        }
    }

    fun pathFor(itemId: String, kind: String, mime: String): File =
        File(itemDirectory(itemId), "$kind.${extension(mime)}")

    fun partFor(target: File): File = File(target.parentFile, "${target.name}.part")

    fun itemDirectory(itemId: String): File {
        val directory = File(root, itemId.replace(SAFE_SEGMENT, "_"))
        require(directory.isDirectory || directory.mkdirs() || directory.isDirectory) {
            "Cannot create item directory: $directory"
        }
        return directory
    }

    fun existingFile(itemId: String, kind: String, localPath: String?): File? {
        localPath?.let { path ->
            val file = File(path)
            if (file.isFile) return file
        }
        val directory = itemDirectory(itemId)
        return directory.listFiles()
            ?.firstOrNull { it.isFile && it.name.startsWith("$kind.") && !it.name.endsWith(".part") }
    }

    fun deleteArtifact(itemId: String, kind: String, localPath: String?) {
        localPath?.let { File(it).delete() }
        itemDirectory(itemId).listFiles()
            ?.filter { it.name.startsWith("$kind.") }
            ?.forEach { it.delete() }
    }

    fun deleteItem(itemId: String) {
        itemDirectory(itemId).deleteRecursively()
    }

    fun deletePath(path: String) {
        File(path).delete()
    }

    fun usableSpace(): Long = root.usableSpace

    private fun extension(mime: String): String = when (mime.lowercase()) {
        "audio/mp4", "audio/x-m4a" -> "m4a"
        "audio/mpeg" -> "mp3"
        "audio/flac", "audio/x-flac" -> "flac"
        "audio/wav", "audio/x-wav" -> "wav"
        "audio/ogg", "audio/opus" -> "ogg"
        "audio/aac" -> "aac"
        "application/epub+zip" -> "epub"
        "application/json" -> "json"
        "image/jpeg" -> "jpg"
        "image/png" -> "png"
        "image/webp" -> "webp"
        else -> mime.substringAfter('/', "bin").replace(SAFE_SEGMENT, "_")
    }
}
