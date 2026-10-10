package info.thewiderlens.claimscout.work

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import info.thewiderlens.claimscout.ClaimScoutApp
import info.thewiderlens.claimscout.MainActivity
import info.thewiderlens.claimscout.R
import info.thewiderlens.claimscout.data.Api

/** Every few hours: ask the PC for new likely matches and notify once per settlement. */
class CheckWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    companion object { const val CHANNEL = "matches" }

    override suspend fun doWork(): Result {
        val store = (applicationContext as ClaimScoutApp).store
        val pairing = store.pairing() ?: return Result.success()
        val items = try {
            Api(pairing) { store.setPairing(pairing.copy(lastGood = it)) }.newSince(0.0).new
        } catch (e: Exception) {
            return Result.success()   // PC off or phone away from home: try next time
        }
        val already = store.notified()
        val fresh = items.filter { it.id !in already }
        if (fresh.isEmpty()) return Result.success()
        if (applicationContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) {
            val nm = NotificationManagerCompat.from(applicationContext)
            fresh.take(5).forEach { s ->
                val open = PendingIntent.getActivity(applicationContext, s.id.hashCode(),
                    Intent(applicationContext, MainActivity::class.java).putExtra("settlement", s.id),
                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
                nm.notify(s.id.hashCode(), NotificationCompat.Builder(applicationContext, CHANNEL)
                    .setSmallIcon(R.drawable.ic_notification).setColor(0xFF0081FE.toInt())
                    .setContentTitle("You may qualify: ${s.title}")
                    .setContentText(listOfNotNull(s.award, s.deadline?.let { "claim by $it" }).joinToString(" · "))
                    .setContentIntent(open).setAutoCancel(true).build())
            }
        }
        store.addNotified(fresh.map { it.id })
        return Result.success()
    }
}
