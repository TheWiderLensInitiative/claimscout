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
            val scheme = if (isSystemInDarkTheme())
                darkColorScheme(primary = Color(0xFF5FC18F), tertiary = Color(0xFFE3A14A))
            else lightColorScheme(primary = Color(0xFF1F6F4A), tertiary = Color(0xFFA55B00))
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
