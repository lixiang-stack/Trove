package dev.trove.app

import android.app.Application
import dev.trove.reader.ReaderDependencies
import dev.trove.reader.ReaderHost

class TroveApplication : Application(), ReaderHost {
    lateinit var container: AppContainer
        private set

    override val readerDependencies: ReaderDependencies?
        get() = if (::container.isInitialized) container.readerDependencies else null

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
