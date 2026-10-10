package info.thewiderlens.claimscout.ui

import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.NumberFormat
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

/** Logos decoded once per app run. A missing entry means "not loaded yet"; a null value means "none". */
object LogoCache {
    private val cache = LruCache<String, Any>(300)
    private object None
    fun peek(id: String): ImageBitmap? = cache.get(id) as? ImageBitmap
    fun known(id: String) = cache.get(id) != null
    fun put(id: String, img: ImageBitmap?) = cache.put(id, img ?: None)
}

private val MONO_COLORS = listOf(0xFF0081FE, 0xFF7C4DFF, 0xFF00897B, 0xFFE65100, 0xFFC2185B, 0xFF5D4037, 0xFF3949AB, 0xFF2E7D32)

/** The company's logo on a white tile, or its initials on a brand-coloured tile when there's no logo. */
@Composable
fun CompanyLogo(vm: Vm, id: String, name: String, hasLogo: Boolean, size: Dp = 52.dp) {
    var img by remember(id) { mutableStateOf(LogoCache.peek(id)) }
    if (hasLogo) LaunchedEffect(id) {
        if (!LogoCache.known(id)) {
            val bytes = runCatching { vm.apiOrNull()?.logo(id) }.getOrNull()
            val bmp = bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }
            LogoCache.put(id, bmp)
            img = bmp
        }
    }
    val shape = RoundedCornerShape(size * 0.24f)
    val bitmap = img
    if (bitmap != null) {
        Surface(Modifier.size(size), shape = shape, color = Color.White,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
            Image(bitmap, name, Modifier.padding(size * 0.06f))
        }
    } else {
        val c = Color(MONO_COLORS[Math.floorMod(name.hashCode(), MONO_COLORS.size)])
        Box(Modifier.size(size).background(c, shape), contentAlignment = Alignment.Center) {
            Text(initials(name), color = Color.White, fontFamily = Montserrat, fontWeight = FontWeight.ExtraBold,
                fontSize = (size.value * 0.36f).sp)
        }
    }
}

fun initials(name: String): String =
    name.split(Regex("[\\s,&/]+")).filter { it.firstOrNull()?.isLetterOrDigit() == true }.take(2)
        .joinToString("") { it.first().uppercase() }.ifEmpty { "?" }

fun money(v: Double): String = NumberFormat.getCurrencyInstance(Locale.US).apply {
    maximumFractionDigits = if (v % 1.0 == 0.0) 0 else 2
}.format(v)

/** "Ends today", "3 days left", or "Ends Jan 19" when it's far off. Second value: urgent (two weeks or less). */
fun deadlineText(iso: String?): Pair<String, Boolean>? {
    val d = iso?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: return null
    val days = ChronoUnit.DAYS.between(LocalDate.now(), d)
    return when {
        days < 0 -> "Closed" to true
        days == 0L -> "Ends today" to true
        days == 1L -> "1 day left" to true
        days <= 45 -> "$days days left" to (days <= 14)
        else -> "Ends " + d.format(DateTimeFormatter.ofPattern("MMM d", Locale.US)) to false
    }
}

/** A small rounded label: deadline, "No proof needed", "Likely", claim status. */
@Composable
fun Badge(text: String, fg: Color, bg: Color) = Box(Modifier.background(bg, RoundedCornerShape(50)).padding(horizontal = 8.dp, vertical = 3.dp)) {
    Text(text, color = fg, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
}

enum class Tone(val day: Long, val night: Long) {
    Green(0xFF1B7F3B, 0xFF6FD08C), Red(0xFFC62828, 0xFFFF8A80), Blue(0xFF0066CC, 0xFF6CB4FF),
    Gray(0xFF5F6670, 0xFFA5ACB6), Amber(0xFFA55B00, 0xFFF0B060)
}

/** Badge in a tone that stays readable in light and dark mode. */
@Composable
fun Badge(text: String, tone: Tone) {
    val fg = Color(if (isSystemInDarkTheme()) tone.night else tone.day)
    Badge(text, fg, fg.copy(alpha = 0.14f))
}
