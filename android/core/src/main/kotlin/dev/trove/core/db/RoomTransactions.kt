package dev.trove.core.db

import android.annotation.SuppressLint
import androidx.room.immediateTransaction
import androidx.room.useWriterConnection
import androidx.room.withTransaction

@SuppressLint("RestrictedApi")
suspend fun <T> TroveDatabase.writeTransaction(block: suspend () -> T): T =
    if (inCompatibilityMode()) {
        withTransaction { block() }
    } else {
        useWriterConnection { transactor ->
            transactor.immediateTransaction { block() }
        }
    }
