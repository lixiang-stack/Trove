package dev.trove.app

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
        setContent {
            TroveApp(sessionViewModel)
        }
    }
}
