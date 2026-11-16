package dev.trove.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import dev.trove.app.session.SessionViewModel

class MainActivity : ComponentActivity() {
    private val sessionViewModel: SessionViewModel by viewModels {
        val container = (application as TroveApplication).container
        SessionViewModel.factory(container.sessionController)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as TroveApplication).container
        handleShare(intent, container)
        setContent {
            TroveApp(sessionViewModel, container)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleShare(intent, (application as TroveApplication).container)
    }

    private fun handleShare(intent: Intent?, container: AppContainer) {
        if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            container.offerSharedText(intent.getStringExtra(Intent.EXTRA_TEXT))
        }
    }
}
