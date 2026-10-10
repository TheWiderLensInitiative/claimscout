package info.thewiderlens.claimscout.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import info.thewiderlens.claimscout.R
import info.thewiderlens.claimscout.data.Claim
import info.thewiderlens.claimscout.data.Detail
import info.thewiderlens.claimscout.data.Profile
import info.thewiderlens.claimscout.data.Row

private fun openUrl(ctx: Context, url: String) =
    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }

private fun copy(ctx: Context, text: String) =
    ctx.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("ClaimScout", text))

@Composable
fun App(vm: Vm) {
    val pairing by vm.pairing.collectAsState()
    if (!vm.loaded) return
    when {
        pairing == null -> PairScreen(vm)
        vm.quizActive -> Onboarding(vm)
        vm.openId != null -> DetailScreen(vm)
        else -> MainScreen(vm)
    }
}

@Composable
fun ErrorText(vm: Vm) = vm.error?.let {
    Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(vertical = 8.dp))
}

@Composable
fun PairScreen(vm: Vm) {
    var link by remember { mutableStateOf("") }
    Scaffold { pad ->
        Column(Modifier.padding(pad).padding(20.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Image(painterResource(R.drawable.brand_logo), "ClaimScout",
                Modifier.fillMaxWidth().padding(vertical = 16.dp).height(200.dp))
            Text("Finds class action settlements you may qualify for. It runs on your own PC, free, with no subscription.")
            Text("1. On your PC, run ClaimScout and open the dashboard (claimscout open).\n" +
                "2. Go to the Phone tab.\n3. Scan the QR code with this phone's camera, or copy the pairing link and paste it here.")
            OutlinedTextField(link, { link = it }, label = { Text("Pairing link") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            Button({ vm.pair(link) }, enabled = link.isNotBlank() && !vm.busy) { Text("Pair") }
            if (vm.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            ErrorText(vm)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: Vm) {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text(vm.tab.label) }, navigationIcon = {
                Image(painterResource(R.drawable.brand_mark), "ClaimScout", Modifier.padding(start = 12.dp, end = 4.dp).size(36.dp))
            })
        },
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { t ->
                    NavigationBarItem(selected = vm.tab == t, onClick = { vm.select(t) }, label = { Text(t.label) },
                        icon = { Icon(when (t) { Tab.Matches -> Icons.Filled.Home; Tab.Browse -> Icons.Filled.Search
                            Tab.Claims -> Icons.Filled.CheckCircle; Tab.Settings -> Icons.Filled.Settings }, null) })
                }
            }
        }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            if (vm.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            Column(Modifier.padding(horizontal = 16.dp)) { ErrorText(vm) }
            when (vm.tab) {
                Tab.Settings -> SettingsScreen(vm)
                else -> ListScreen(vm)
            }
        }
    }
}

@Composable
fun ListScreen(vm: Vm) {
    Column(Modifier.padding(horizontal = 16.dp)) {
        if (vm.tab == Tab.Browse) {
            OutlinedTextField(vm.query, { vm.query = it }, label = { Text("Search settlements") }, singleLine = true,
                modifier = Modifier.fillMaxWidth(), trailingIcon = { IconButton({ vm.reload() }) { Icon(Icons.Filled.Search, "Search") } })
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(vm.noProofOnly, { vm.noProofOnly = !vm.noProofOnly; vm.reload() }, label = { Text("No proof needed") })
            }
        }
        vm.status?.let { s ->
            if (vm.tab == Tab.Matches) {
                Text("${s.likely} likely · ${s.maybe} maybe · ${s.open} open settlements" + if (s.refreshing) " · checking…" else "",
                    style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 8.dp))
                if (s.unanswered > 0) Card(Modifier.fillMaxWidth().clickable { vm.startQuiz(full = false) }) {
                    Column(Modifier.padding(12.dp)) {
                        Text("${s.unanswered} settlement${if (s.unanswered == 1) "" else "s"} to check", fontWeight = FontWeight.SemiBold)
                        Text("Answer a few quick questions to see if they fit you.", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            items(vm.rows, key = { it.id }) { RowCard(it) { vm.open(it.id) } }
            if (vm.rows.isEmpty() && !vm.busy) item {
                Text(when (vm.tab) { Tab.Claims -> "Claims you mark as filed show up here."
                    Tab.Matches -> "No matches yet. Fill in your profile, or browse every open settlement."
                    else -> "Nothing found." }, Modifier.padding(16.dp))
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
fun Verdict(v: String?) {
    val (text, color) = when (v) {
        "likely" -> "Likely you" to MaterialTheme.colorScheme.primary
        "maybe" -> "Maybe" to MaterialTheme.colorScheme.tertiary
        "unlikely" -> "Unlikely" to MaterialTheme.colorScheme.outline
        else -> return
    }
    Text(text, color = color, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
}

@Composable
fun RowCard(r: Row, onClick: () -> Unit) = Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(r.title, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Verdict(r.verdict)
        }
        Text(listOfNotNull(r.deadline?.let { "Claim by $it" } ?: "No deadline listed", r.award,
            when (r.proof_needed) { 0 -> "no proof needed"; 1 -> "proof needed"; else -> null },
            r.states.takeIf { it.isNotEmpty() }?.let { it.joinToString() + " only" },
            r.claim_status?.let { "claim $it" }, r.proofs.takeIf { it > 0 }?.let { "$it proof found" })
            .joinToString(" · "), style = MaterialTheme.typography.bodySmall)
        r.reason?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DetailScreen(vm: Vm) {
    val ctx = LocalContext.current
    BackHandler { vm.open(null); vm.reload() }
    var filing by remember { mutableStateOf(false) }
    Scaffold(topBar = {
        TopAppBar(title = { Text("Settlement") }, navigationIcon = {
            IconButton({ vm.open(null); vm.reload() }) { Icon(Icons.Filled.ArrowBack, "Back") }
        })
    }) { pad ->
        val d = vm.detail
        Column(Modifier.padding(pad).padding(16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (vm.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            ErrorText(vm)
            if (d == null) return@Column
            Text(d.title, style = MaterialTheme.typography.headlineSmall)
            d.match?.let { m ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Verdict(m.verdict)
                    m.reason?.let { Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f)) }
                }
            }
            Fact("Claim deadline", d.deadline ?: "not listed")
            Fact("Potential award", d.award ?: "TBD")
            Fact("Who's eligible", d.eligibility ?: "-")
            Fact("Proof needed", d.proof ?: "not stated")
            d.case_name?.let { Text(it, style = MaterialTheme.typography.bodySmall) }

            Text("Only file if you qualify. Claims are made under penalty of perjury.",
                color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                d.claim_url?.let { Button({ openUrl(ctx, it) }) { Text("Open claim form") } }
                d.website?.let { OutlinedButton({ openUrl(ctx, it) }) { Text("Website") } }
            }

            HorizontalDivider()
            Text("Proof from your email", style = MaterialTheme.typography.titleMedium)
            ProofSection(vm, d, ctx)

            HorizontalDivider()
            ClaimSection(vm, d, onFile = { filing = true })
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton({ vm.recheck(d.id) }) { Text("Check again") }
                TextButton({ vm.dismiss(d.id) }) { Text("Not for me") }
                d.url?.let { TextButton({ openUrl(ctx, it) }) { Text("Source") } }
            }
        }
        if (filing && d != null) FileDialog(d.claim, onDismiss = { filing = false }) { c -> vm.saveClaim(d.id, c); filing = false }
    }
}

@Composable
fun Fact(label: String, value: String) = Column {
    Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.outline)
    Text(value)
}

@Composable
fun ProofSection(vm: Vm, d: Detail, ctx: Context) {
    val accounts by vm.accounts.collectAsState()
    d.proof_plan?.let { p ->
        val what = (p.senders.map { "from $it" } + p.keywords.map { "“$it”" }).joinToString(", ")
        if (what.isNotEmpty()) Text("Searches: $what" + listOfNotNull(p.after?.let { " after $it" }, p.before?.let { " before $it" }).joinToString(""),
            style = MaterialTheme.typography.bodySmall)
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button({ vm.findProof() }, enabled = !vm.findingProof) {
            Text(if (accounts.isEmpty()) "Find proof (connect email first)" else "Find proof in my email")
        }
        if (vm.findingProof) CircularProgressIndicator(Modifier.height(24.dp))
    }
    vm.proofNote?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    d.proofs.forEach { p ->
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(p.summary ?: p.subject ?: "Email", fontWeight = FontWeight.SemiBold)
                Text(listOfNotNull(p.date, p.kind?.replace('_', ' '), p.sender, p.account).joinToString(" · "), style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    p.order_number?.let { TextButton({ copy(ctx, it) }) { Text("Copy order #$it") } }
                    p.amount?.let { TextButton({ copy(ctx, it) }) { Text("Copy $it") } }
                    p.id?.let { id -> TextButton({ vm.deleteProof(id) }) { Text("Remove") } }
                }
            }
        }
    }
}

@Composable
fun ClaimSection(vm: Vm, d: Detail, onFile: () -> Unit) {
    val c = d.claim
    if (c == null) {
        OutlinedButton(onFile) { Text("I filed a claim") }
    } else {
        Text("Your claim: ${c.status}" + (c.claim_number?.takeIf { it.isNotBlank() }?.let { " · #$it" } ?: ""), style = MaterialTheme.typography.titleMedium)
        listOfNotNull(c.filed_at?.takeIf { it.isNotBlank() }?.let { "Filed $it" }, c.paid?.takeIf { it.isNotBlank() }?.let { "Paid $it" },
            c.notes?.takeIf { it.isNotBlank() }).forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onFile) { Text("Update") }
            TextButton({ vm.saveClaim(d.id, null) }) { Text("Remove") }
        }
    }
}

@Composable
fun FileDialog(existing: Claim?, onDismiss: () -> Unit, onSave: (Claim) -> Unit) {
    var status by remember { mutableStateOf(existing?.status ?: "filed") }
    var number by remember { mutableStateOf(existing?.claim_number ?: "") }
    var filed by remember { mutableStateOf(existing?.filed_at ?: java.time.LocalDate.now().toString()) }
    var paid by remember { mutableStateOf(existing?.paid ?: "") }
    var notes by remember { mutableStateOf(existing?.notes ?: "") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Your claim") },
        confirmButton = { Button({ onSave(Claim(status, number, filed, existing?.expected, paid, notes)) }) { Text("Save") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("filed", "approved", "paid", "denied").forEach { s -> FilterChip(status == s, { status = s }, label = { Text(s) }) }
                }
                OutlinedTextField(number, { number = it }, label = { Text("Claim / confirmation number") }, singleLine = true)
                OutlinedTextField(filed, { filed = it }, label = { Text("Filed on") }, singleLine = true)
                if (status == "paid") OutlinedTextField(paid, { paid = it }, label = { Text("Amount paid") }, singleLine = true)
                OutlinedTextField(notes, { notes = it }, label = { Text("Notes") })
            }
        })
}

@Composable
fun SettingsScreen(vm: Vm) {
    val ctx = LocalContext.current
    val accounts by vm.accounts.collectAsState()
    var addingGmail by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { if (vm.profile == null) vm.loadProfile() }
    Column(Modifier.padding(horizontal = 16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Email accounts", style = MaterialTheme.typography.titleMedium)
        Text("Used only to find proof (receipts, order emails, breach notices) when you tap “Find proof”. " +
            "Mail is searched from this phone, read-only; only matching emails go to your PC.", style = MaterialTheme.typography.bodySmall)
        accounts.forEach { a ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${if (a.kind == "gmail") "Gmail" else "Outlook"} · ${a.address}", Modifier.weight(1f))
                TextButton({ vm.removeAccount(a) }) { Text("Remove") }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton({ addingGmail = true }) { Text("Add Gmail") }
            OutlinedButton({ vm.startOutlook() }, enabled = vm.outlookCode == null) { Text("Add Outlook") }
        }
        OutlookSetup(vm, ctx)
        if (addingGmail) GmailDialog(vm) { addingGmail = false }

        HorizontalDivider()
        Text("Your profile", style = MaterialTheme.typography.titleMedium)
        Text("Built from your questionnaire answers. Edit it here, or redo the questions.", style = MaterialTheme.typography.bodySmall)
        OutlinedButton({ vm.startQuiz(full = false, redo = true) }) { Text("Redo the questionnaire") }
        vm.profile?.let { ProfileEditor(it) { p -> vm.saveProfile(p) } }

        HorizontalDivider()
        Text("Your PC", style = MaterialTheme.typography.titleMedium)
        vm.status?.let { Text("ClaimScout ${it.version} · ${it.open} open settlements", style = MaterialTheme.typography.bodySmall) }
        Text("AI settings (local model or OpenRouter) are on the PC dashboard.", style = MaterialTheme.typography.bodySmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton({ vm.checkNow() }) { Text("Check for new settlements") }
            TextButton({ vm.unpair() }) { Text("Unpair") }
        }
        Text("ClaimScout is free and open source. It isn't a law firm or a settlement administrator. " +
            "Settlement listings come from public sources; always read the official notice.", style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(24.dp))
    }
}

/** The Microsoft client ID box (until one is set) and the sign-in code while Outlook is connecting. */
@Composable
fun OutlookSetup(vm: Vm, ctx: Context) {
    if (vm.error?.contains("client ID") == true || (vm.msClientId.isEmpty() && vm.outlookCode == null && vm.askedForMsId)) {
        OutlinedTextField(vm.msClientId, { vm.msClientId = it.trim() }, label = { Text("Microsoft app client ID (one-time setup)") },
            singleLine = true, modifier = Modifier.fillMaxWidth())
        TextButton({ openUrl(ctx, "https://github.com/TheWiderLensInitiative/claimscout/blob/main/docs/OUTLOOK.md") }) { Text("How to get one (free, 3 minutes)") }
    }
    vm.outlookCode?.let { dc ->
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Enter this code at ${dc.verifyUrl}:")
                Text(dc.userCode, style = MaterialTheme.typography.headlineMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button({ copy(ctx, dc.userCode); openUrl(ctx, dc.verifyUrl) }) { Text("Copy code and open") }
                }
                Text("Waiting for you to sign in…", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
fun ProfileEditor(p: Profile, onSave: (Profile) -> Unit) {
    var companies by remember(p) { mutableStateOf(p.companies.joinToString("\n")) }
    var states by remember(p) { mutableStateOf(p.states.joinToString(", ")) }
    var past by remember(p) { mutableStateOf(p.past_states.joinToString(", ")) }
    var about by remember(p) { mutableStateOf(p.about) }
    val split = { s: String -> s.split(',', '\n').map { it.trim() }.filter { it.isNotEmpty() } }
    OutlinedTextField(companies, { companies = it }, label = { Text("Companies, products, services (one per line)") },
        modifier = Modifier.fillMaxWidth(), minLines = 3)
    OutlinedTextField(states, { states = it }, label = { Text("State you live in (e.g. TX)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(past, { past = it }, label = { Text("States you lived in before") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(about, { about = it }, label = { Text("Anything else (devices, cars, banks, breach letters…)") },
        modifier = Modifier.fillMaxWidth(), minLines = 2)
    Button({ onSave(p.copy(companies = split(companies), states = split(states), past_states = split(past), about = about)) }) {
        Text("Save and re-check")
    }
}

@Composable
fun GmailDialog(vm: Vm, onDone: () -> Unit) {
    val ctx = LocalContext.current
    var address by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDone, title = { Text("Add Gmail") },
        confirmButton = { Button({ vm.addGmail(address, password, onDone) }, enabled = address.contains('@') && password.length >= 16 && !vm.busy) { Text("Connect") } },
        dismissButton = { TextButton(onDone) { Text("Cancel") } },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Gmail needs an app password (it requires 2-Step Verification). It only lets ClaimScout read mail over IMAP and can be revoked anytime.",
                    style = MaterialTheme.typography.bodySmall)
                TextButton({ openUrl(ctx, "https://myaccount.google.com/apppasswords") }) { Text("Create an app password") }
                OutlinedTextField(address, { address = it }, label = { Text("Gmail address") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                OutlinedTextField(password, { password = it }, label = { Text("App password") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation())
                if (vm.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                ErrorText(vm)
            }
        })
}
