package info.thewiderlens.claimscout.ui

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import info.thewiderlens.claimscout.R

/** Montserrat (the logo's lettering, SIL OFL) for headings and amounts; the system font for reading. */
@OptIn(androidx.compose.ui.text.ExperimentalTextApi::class)
private fun montserrat(w: Int) = Font(R.font.montserrat, FontWeight(w), variationSettings = FontVariation.Settings(FontVariation.weight(w)))

@OptIn(androidx.compose.ui.text.ExperimentalTextApi::class)
val Montserrat = FontFamily(montserrat(500), montserrat(600), montserrat(700), montserrat(800))

fun brandTypography(): Typography {
    val t = Typography()
    fun TextStyle.m(w: Int) = copy(fontFamily = Montserrat, fontWeight = FontWeight(w))
    return t.copy(
        displaySmall = t.displaySmall.m(800), headlineLarge = t.headlineLarge.m(800),
        headlineMedium = t.headlineMedium.m(800), headlineSmall = t.headlineSmall.m(700).copy(fontSize = 22.sp),
        titleLarge = t.titleLarge.m(700), titleMedium = t.titleMedium.m(700), titleSmall = t.titleSmall.m(700),
        labelLarge = t.labelLarge.m(600),
    )
}
