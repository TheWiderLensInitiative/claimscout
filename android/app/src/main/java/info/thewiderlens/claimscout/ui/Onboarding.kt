package info.thewiderlens.claimscout.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import info.thewiderlens.claimscout.R
import info.thewiderlens.claimscout.data.QItem

private val STATES = listOf(
    "AL" to "Alabama", "AK" to "Alaska", "AZ" to "Arizona", "AR" to "Arkansas", "CA" to "California", "CO" to "Colorado",
    "CT" to "Connecticut", "DE" to "Delaware", "DC" to "Washington, D.C.", "FL" to "Florida", "GA" to "Georgia", "HI" to "Hawaii",
    "ID" to "Idaho", "IL" to "Illinois", "IN" to "Indiana", "IA" to "Iowa", "KS" to "Kansas", "KY" to "Kentucky",
    "LA" to "Louisiana", "ME" to "Maine", "MD" to "Maryland", "MA" to "Massachusetts", "MI" to "Michigan", "MN" to "Minnesota",
    "MS" to "Mississippi", "MO" to "Missouri", "MT" to "Montana", "NE" to "Nebraska", "NV" to "Nevada", "NH" to "New Hampshire",
    "NJ" to "New Jersey", "NM" to "New Mexico", "NY" to "New York", "NC" to "North Carolina", "ND" to "North Dakota",
    "OH" to "Ohio", "OK" to "Oklahoma", "OR" to "Oregon", "PA" to "Pennsylvania", "RI" to "Rhode Island",
    "SC" to "South Carolina", "SD" to "South Dakota", "TN" to "Tennessee", "TX" to "Texas", "UT" to "Utah", "VT" to "Vermont",
    "VA" to "Virginia", "WA" to "Washington", "WV" to "West Virginia", "WI" to "Wisconsin", "WY" to "Wyoming", "PR" to "Puerto Rico",
)

/** The onboarding questionnaire (first run) and the "new settlements" questions (later). */
@Composable
fun Onboarding(vm: Vm) {
    BackHandler(enabled = !vm.quizFull) { vm.quizActive = false }
    Scaffold { pad ->
        Column(Modifier.padding(pad).fillMaxSize().padding(horizontal = 20.dp)) {
            if (vm.busy) LinearProgressIndicator(Modifier.fillMaxWidth()) else Spacer(Modifier.height(4.dp))
            ErrorText(vm)
            when (vm.step) {
                Step.Welcome -> Welcome(vm)
                Step.HomeState -> HomeState(vm)
                Step.PastStates -> PastStates(vm)
                Step.Pick -> Pick(vm)
                Step.Ask -> Ask(vm)
                Step.Email -> EmailStep(vm)
                Step.Notify -> NotifyStep(vm)
                Step.Done -> DoneStep(vm)
            }
        }
    }
}

@Composable
private fun Page(title: String, sub: String? = null, footer: @Composable RowScope.() -> Unit, body: @Composable () -> Unit) =
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
            sub?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            body()
            Spacer(Modifier.height(8.dp))
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) { footer() }
    }

@Composable
private fun Welcome(vm: Vm) = Page("Let's find money you're owed",
    footer = { Button({ vm.step = Step.HomeState }, Modifier.fillMaxWidth()) { Text("Get started") } }) {
    Image(painterResource(R.drawable.brand_logo), "ClaimScout", Modifier.fillMaxWidth().height(180.dp).padding(vertical = 8.dp))
    Text("Answer a few quick questions once. ClaimScout turns the open class action settlements into simple " +
        "“have you used this?” questions, builds your profile from your answers, and keeps matching you as new settlements appear.")
    Text("About 3 minutes. Your answers stay on your PC.", style = MaterialTheme.typography.bodySmall)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HomeState(vm: Vm) = Page("Where do you live now?", "Some settlements only cover people in certain states.",
    footer = {
        TextButton({ vm.homeState = ""; vm.step = Step.PastStates }) { Text("Skip") }
        Spacer(Modifier.weight(1f))
        Button({ vm.step = Step.PastStates }, enabled = vm.homeState.isNotEmpty()) { Text("Next") }
    }) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        STATES.forEach { (code, name) -> FilterChip(vm.homeState == code, { vm.homeState = code }, label = { Text(name) }) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PastStates(vm: Vm) = Page("Where else have you lived?", "Any state in the last 10 years or so. Skip if none.",
    footer = {
        TextButton({ vm.step = Step.HomeState }) { Text("Back") }
        Spacer(Modifier.weight(1f))
        Button({ vm.saveStates() }, enabled = !vm.busy) { Text(if (vm.pastStates.isEmpty()) "None, next" else "Next") }
    }) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        STATES.filter { it.first != vm.homeState }.forEach { (code, name) ->
            FilterChip(code in vm.pastStates, { vm.pastStates = if (code in vm.pastStates) vm.pastStates - code else vm.pastStates + code },
                label = { Text(name) })
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Pick(vm: Vm) {
    val groups = vm.quiz?.groups ?: emptyList()
    val g = groups.getOrNull(vm.groupIndex)
    if (g == null) { Text("Loading settlements…", Modifier.padding(top = 24.dp)); return }
    Page(g.category, g.prompt, footer = {
        TextButton({ vm.skipQuestions() }) { Text("Finish later") }
        Spacer(Modifier.weight(1f))
        Button({ vm.finishGroup() }, enabled = !vm.busy) { Text(if (vm.picked.isEmpty()) "None of these" else "Next") }
    }) {
        Text("Page ${vm.groupIndex + 1} of ${groups.size}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            g.items.forEach { item ->
                FilterChip(item.id in vm.picked, { vm.togglePick(item.id) }, label = { Text(item.label) },
                    leadingIcon = { CompanyLogo(vm, item.id, item.label, item.logo, 22.dp) })
            }
        }
        Text("Pick anything you've bought, used, or been a customer, patient or member of. You'll get one quick question about each.",
            style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun Ask(vm: Vm) {
    val item: QItem = vm.toAsk.firstOrNull() ?: return
    Page("", footer = {
        OutlinedButton({ vm.answer(item, "no") }, Modifier.weight(1f), enabled = !vm.busy) { Text("No") }
        OutlinedButton({ vm.answer(item, "unsure") }, Modifier.weight(1f), enabled = !vm.busy) { Text("Not sure") }
        Button({ vm.answer(item, "yes") }, Modifier.weight(1f), enabled = !vm.busy) { Text("Yes") }
    }) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            CompanyLogo(vm, item.id, item.label, item.logo, 64.dp)
            Spacer(Modifier.padding(start = 14.dp))
            Column(Modifier.weight(1f)) {
                Text(item.label, style = MaterialTheme.typography.headlineSmall)
                item.amountText()?.let { Text(it, color = MaterialTheme.colorScheme.primary, fontFamily = Montserrat, fontWeight = FontWeight.ExtraBold) }
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(item.question ?: "Does this describe you?", style = MaterialTheme.typography.titleMedium)
                item.eligibility?.takeIf { it.isNotBlank() }?.let {
                    Text("Who qualifies: $it", style = MaterialTheme.typography.bodyMedium)
                }
                Text(listOfNotNull(item.award, item.deadline?.let { "claim by $it" },
                    when (item.proof_needed) { 0 -> "no proof needed"; 1 -> "proof needed"; else -> null }).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Text(item.title, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (vm.toAsk.size > 1) Text("${vm.toAsk.size - 1} more on this page", style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
private fun EmailStep(vm: Vm) {
    val accounts by vm.accounts.collectAsState()
    var addingGmail by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    Page("Connect your email (optional)",
        "Many claims need proof: a receipt, an order email, a breach notice. ClaimScout can search your email for it " +
            "when you ask, read-only, from this phone. Only matching emails go to your PC.",
        footer = {
            Spacer(Modifier.weight(1f))
            Button({ vm.nextFromEmail() }) { Text(if (accounts.isEmpty()) "Skip for now" else "Next") }
        }) {
        accounts.forEach { Text("✓ ${if (it.kind == "gmail") "Gmail" else "Outlook"} · ${it.address}", color = MaterialTheme.colorScheme.primary) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton({ addingGmail = true }) { Text("Add Gmail") }
            OutlinedButton({ vm.startOutlook() }, enabled = vm.outlookCode == null) { Text("Add Outlook") }
        }
        OutlookSetup(vm, ctx)
        if (addingGmail) GmailDialog(vm) { addingGmail = false }
    }
}

@Composable
private fun NotifyStep(vm: Vm) {
    val ctx = LocalContext.current
    val needs = Build.VERSION.SDK_INT >= 33 &&
        ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { vm.nextFromNotify() }
    Page("Get told about new money", "When a new settlement fits your answers, ClaimScout lets you know, including a few new questions to answer.",
        footer = {
            TextButton({ vm.nextFromNotify() }) { Text("Not now") }
            Spacer(Modifier.weight(1f))
            Button({ if (needs) ask.launch(Manifest.permission.POST_NOTIFICATIONS) else vm.nextFromNotify() }) {
                Text(if (needs) "Allow notifications" else "Next")
            }
        }) {}
}

@Composable
private fun DoneStep(vm: Vm) {
    val s = vm.status
    Page(if ((s?.likely ?: 0) > 0) "You may qualify for ${s!!.likely} settlement${if (s.likely == 1) "" else "s"}" else "All set",
        footer = { Button({ vm.finishQuiz() }, Modifier.fillMaxWidth()) { Text("See my matches") } }) {
        Text(if ((s?.likely ?: 0) > 0) "Open each one to check the details, find proof in your email, and file on the official claim site."
            else "Nothing matched yet. ClaimScout keeps checking every few hours and will ask you about new settlements.")
        if ((s?.unanswered ?: 0) > 0) Text("${s!!.unanswered} settlements are still waiting for an answer; you can finish them from the For you tab.",
            style = MaterialTheme.typography.bodySmall)
        Text("Your answers built your profile. You can change it anytime in Settings.", style = MaterialTheme.typography.bodySmall)
    }
}

private fun QItem.amountText(): String? = award?.let { a ->
    Regex("""\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\b""", RegexOption.IGNORE_CASE).findAll(a)
        .mapNotNull { m -> m.groupValues[1].replace(",", "").toDoubleOrNull()?.let { if (m.groupValues[2].isNotEmpty()) it * 1000 else it } }
        .filter { it <= 100_000 }.maxOrNull()?.let { "Up to " + money(it) }
}
