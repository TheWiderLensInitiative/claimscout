package info.thewiderlens.claimscout

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color
import info.thewiderlens.claimscout.ui.App
import info.thewiderlens.claimscout.ui.Vm

class MainActivity : ComponentActivity() {
    private val vm: Vm by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handle(intent)
        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        setContent {
            // Logo blue is #0081FE; buttons use a deeper blue by day (white text passes WCAG AA) and a lighter one at night.
            val scheme = if (isSystemInDarkTheme())
                darkColorScheme(primary = Color(0xFF4DA3FF), onPrimary = Color(0xFF0B1A2B), primaryContainer = Color(0xFF0B3A6B),
                    onPrimaryContainer = Color(0xFFD6E8FF), secondaryContainer = Color(0xFF233041), tertiary = Color(0xFFE3A14A),
                    background = Color(0xFF121314), surface = Color(0xFF121314), surfaceContainer = Color(0xFF1C1D20),
                    surfaceContainerHighest = Color(0xFF26282C), surfaceContainerHigh = Color(0xFF222427))
            else lightColorScheme(primary = Color(0xFF0066CC), onPrimary = Color.White, primaryContainer = Color(0xFFD6E8FF),
                onPrimaryContainer = Color(0xFF00305F), secondaryContainer = Color(0xFFDDE8F6), tertiary = Color(0xFFA55B00),
                background = Color.White, surface = Color.White, surfaceContainer = Color(0xFFF3F5F8),
                surfaceContainerHighest = Color(0xFFEDF0F4), surfaceContainerHigh = Color(0xFFF0F2F6), onSurface = Color(0xFF191A1C))
            MaterialTheme(colorScheme = scheme) { App(vm) }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    private fun handle(intent: Intent?) {
        intent?.data?.takeIf { it.scheme == "claimscout" }?.let { vm.pair(it.toString()) }
        intent?.getStringExtra("settlement")?.let { vm.open(it) }
    }
}
