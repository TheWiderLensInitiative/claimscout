package info.thewiderlens.claimscout

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import info.thewiderlens.claimscout.data.Store
import info.thewiderlens.claimscout.work.CheckWorker
import java.util.concurrent.TimeUnit

class ClaimScoutApp : Application() {
    val store by lazy { Store(this) }

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CheckWorker.CHANNEL, "New settlements for you", NotificationManager.IMPORTANCE_DEFAULT))
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("check", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<CheckWorker>(6, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build())
    }
}
