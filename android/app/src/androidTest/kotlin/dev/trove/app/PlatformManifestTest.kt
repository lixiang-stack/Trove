package dev.trove.app

import android.content.ComponentName
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PlatformManifestTest {
    @Test
    fun requiredPermissionsAreDeclared() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val declared = context.packageManager
            .getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS)
            .requestedPermissions
            .orEmpty()
            .toSet()
        val required = setOf(
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
            "android.permission.FOREGROUND_SERVICE",
            "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK",
            "android.permission.FOREGROUND_SERVICE_DATA_SYNC",
        )
        assertTrue(declared.containsAll(required))
    }

    @Test
    fun foregroundServicesUseExpectedTypes() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val pm = context.packageManager
        val playback = pm.getServiceInfo(
            ComponentName(context, "dev.trove.playback.TrovePlaybackService"),
            0,
        )
        assertEquals(
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
            playback.foregroundServiceType,
        )
        val downloads = pm.getServiceInfo(
            ComponentName(context, "androidx.work.impl.foreground.SystemForegroundService"),
            0,
        )
        assertEquals(
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            downloads.foregroundServiceType,
        )
    }
}
