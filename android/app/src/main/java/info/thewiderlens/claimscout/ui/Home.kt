package info.thewiderlens.claimscout.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import info.thewiderlens.claimscout.R
import info.thewiderlens.claimscout.data.Detail
import info.thewiderlens.claimscout.data.Row

val CATEGORIES = listOf("Data breaches & privacy", "Cars", "Insurance", "Banking, credit & fees", "Health & medicine",
    "Work", "Home & products", "Shopping, services & housing", "Something else")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: Vm) {
    Scaffold(
        topBar = {
            TopAppBar(title = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Image(painterResource(R.drawable.brand_mark), null, Modifier.size(34.dp))
                    Spacer(Modifier.width(10.dp))
                    Text(vm.tab.label, style = MaterialTheme.typography.titleLarge)
                }
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
            if (vm.busy) LinearProgressIndicator(Modifier.fillMaxWidth()) else Spacer(Modifier.height(4.dp))
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
    val rows = if (vm.tab == Tab.Browse && vm.sortByPay) vm.rows.sortedByDescending { it.amount ?: -1.0 } else vm.rows
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp)) {
        when (vm.tab) {
            Tab.Matches -> item { Hero(vm) }
            Tab.Browse -> item { BrowseFilters(vm) }
            Tab.Claims -> item { ClaimsHeader(vm) }
            else -> {}
        }
        if (vm.tab == Tab.Matches && rows.isNotEmpty()) item {
            Text("Ready to file", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp))
        }
        items(rows, key = { it.id }) { SettlementCard(vm, it) { vm.open(it.id) } }
        if (rows.isEmpty() && !vm.busy) item {
            Text(when (vm.tab) {
                Tab.Claims -> "Claims you mark as filed show up here, with their status and payout."
                Tab.Matches -> "No matches yet. Answer the questions above, or browse every open settlement."
                else -> "Nothing found."
            }, Modifier.padding(vertical = 24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** The blue card on "For you": how much the likely matches could pay, and new questions waiting. */
@Composable
fun Hero(vm: Vm) {
    val s = vm.status ?: return
    Box(Modifier.fillMaxWidth().background(
        Brush.linearGradient(listOf(Color(0xFF0081FE), Color(0xFF0057B8))), RoundedCornerShape(20.dp)).padding(20.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("You could claim up to", color = Color.White.copy(alpha = 0.85f), fontWeight = FontWeight.SemiBold)
            Text(money(s.potential.toDouble()), color = Color.White, fontFamily = Montserrat, fontWeight = FontWeight.ExtraBold, fontSize = 40.sp)
            Text(buildString {
                append("from ${s.likely} settlement${if (s.likely == 1) "" else "s"} that fit you")
                if (s.potential_unknown > 0) append(" (+${s.potential_unknown} with amounts still to be set)")
            }, color = Color.White.copy(alpha = 0.9f), style = MaterialTheme.typography.bodyMedium)
            if (s.unanswered > 0) {
                Spacer(Modifier.height(6.dp))
                Button({ vm.startQuiz(full = false) }, colors = ButtonDefaults.buttonColors(Color.White, Color(0xFF0057B8))) {
                    Text("Check ${s.unanswered} new settlement${if (s.unanswered == 1) "" else "s"}")
                }
            }
            if (s.refreshing) Text("Looking for new settlements…", color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
fun BrowseFilters(vm: Vm) = Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
    OutlinedTextField(vm.query, { vm.query = it }, placeholder = { Text("Search companies or products") }, singleLine = true,
        shape = RoundedCornerShape(50), modifier = Modifier.fillMaxWidth(),
        leadingIcon = { Icon(Icons.Filled.Search, null) },
        trailingIcon = { TextButton({ vm.reload() }) { Text("Go") } })
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        item { FilterChip(vm.category.isEmpty(), { vm.category = ""; vm.reload() }, label = { Text("All") }) }
        items(CATEGORIES) { c -> FilterChip(vm.category == c, { vm.category = if (vm.category == c) "" else c; vm.reload() }, label = { Text(c) }) }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(vm.noProofOnly, { vm.noProofOnly = !vm.noProofOnly; vm.reload() }, label = { Text("No proof needed") })
        FilterChip(vm.sortByPay, { vm.sortByPay = !vm.sortByPay }, label = { Text("Highest payout") })
    }
}

@Composable
fun ClaimsHeader(vm: Vm) {
    val filed = vm.rows.count { it.claim_status != null }
    val paid = vm.rows.count { it.claim_status == "paid" }
    if (filed > 0) Text("$filed claim${if (filed == 1) "" else "s"} filed · $paid paid", style = MaterialTheme.typography.titleMedium)
}

/** A settlement in a list: logo, company, what it's about, badges, and the payout on the right. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SettlementCard(vm: Vm, r: Row, onClick: () -> Unit) = Card(
    Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(16.dp),
    colors = CardDefaults.cardColors(MaterialTheme.colorScheme.surfaceContainer)) {
    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        CompanyLogo(vm, r.id, r.label ?: r.title, r.logo)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(r.label ?: r.title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(r.title, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier.padding(top = 2.dp)) {
                when (r.claim_status) {
                    null -> {}
                    "paid" -> Badge("Paid", Tone.Green)
                    "denied" -> Badge("Denied", Tone.Red)
                    else -> Badge(r.claim_status.replaceFirstChar { it.uppercase() }, Tone.Blue)
                }
                if (r.claim_status == null) deadlineText(r.deadline)?.let { (t, urgent) -> Badge(t, if (urgent) Tone.Red else Tone.Gray) }
                if (r.proof_needed == 0) Badge("No proof", Tone.Green)
                if (r.verdict == "likely" && vm.tab != Tab.Matches) Badge("Fits you", Tone.Blue)
            }
        }
        Spacer(Modifier.width(8.dp))
        Payout(r.amount, r.award)
    }
}

@Composable
fun Payout(amount: Double?, award: String?) = Column(horizontalAlignment = Alignment.End) {
    if (amount != null) {
        Text("up to", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(money(amount), fontFamily = Montserrat, fontWeight = FontWeight.ExtraBold, fontSize = 18.sp,
            color = MaterialTheme.colorScheme.primary)
    } else {
        Text(if (award.isNullOrBlank() || award.equals("TBD", true)) "TBD" else "Varies", fontFamily = Montserrat,
            fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DetailScreen(vm: Vm) {
    val ctx = LocalContext.current
    val back: () -> Unit = { vm.open(null); vm.reload() }
    BackHandler { back() }
    var filing by remember { mutableStateOf(false) }
    val d = vm.detail
    Scaffold(
        topBar = { TopAppBar(title = {}, navigationIcon = { IconButton(back) { Icon(Icons.Filled.ArrowBack, "Back") } }) },
        bottomBar = {
            if (d != null) Surface(tonalElevation = 3.dp, shadowElevation = 8.dp) {
                Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(16.dp, 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    d.website?.let { OutlinedButton({ openUrl(ctx, it) }, Modifier.weight(1f)) { Text("Learn more") } }
                    d.claim_url?.let {
                        Button({ openUrl(ctx, it) }, Modifier.weight(1.4f)) { Text(if (d.claim == null) "File claim" else "Open claim site") }
                    }
                }
            }
        }
    ) { pad ->
        Column(Modifier.padding(pad).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            if (vm.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            ErrorText(vm)
            if (d == null) return@Column
            DetailHeader(vm, d)
            d.match?.reason?.takeIf { it.isNotBlank() }?.let { reason ->
                val fits = d.match.verdict == "likely"
                Surface(color = if (fits) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainerHigh,
                    shape = RoundedCornerShape(14.dp)) {
                    Column(Modifier.fillMaxWidth().padding(14.dp)) {
                        Text(when (d.match.verdict) { "likely" -> "Looks like you qualify"; "maybe" -> "You might qualify"; "unlikely" -> "Probably not for you"; else -> "Your match" },
                            style = MaterialTheme.typography.titleSmall)
                        Text(reason, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            Section("Who qualifies") { Text(d.eligibility ?: "See the settlement website.") }
            Section("Proof needed") {
                Text(d.proof ?: "Not stated.")
                Spacer(Modifier.height(8.dp))
                ProofSection(vm, d, ctx)
            }
            Section("Your claim") { ClaimSection(vm, d, onFile = { filing = true }) }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                d.case_name?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                Text("Only file if you qualify: claims are made under penalty of perjury. ClaimScout isn't affiliated with " +
                    "the companies shown; logos belong to their owners.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row {
                    TextButton({ vm.recheck(d.id) }) { Text("Check again") }
                    TextButton({ vm.dismiss(d.id) }) { Text("Not for me") }
                    d.url?.let { TextButton({ openUrl(ctx, it) }) { Text("Source") } }
                }
            }
            Spacer(Modifier.height(8.dp))
        }
        if (filing && d != null) FileDialog(d.claim, onDismiss = { filing = false }) { c -> vm.saveClaim(d.id, c); filing = false }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DetailHeader(vm: Vm, d: Detail) = Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        CompanyLogo(vm, d.id, d.label ?: d.title, d.logo, 72.dp)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(d.label ?: d.title, style = MaterialTheme.typography.headlineSmall)
            Text(d.title, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(d.amount?.let { "Up to " + money(it) } ?: (d.award ?: "Award TBD"), fontFamily = Montserrat,
            fontWeight = FontWeight.ExtraBold, fontSize = if (d.amount != null) 28.sp else 18.sp, color = MaterialTheme.colorScheme.primary)
    }
    if (d.amount != null && d.award != null) Text(d.award, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        deadlineText(d.deadline)?.let { (t, urgent) -> Badge(if (t.startsWith("Ends ") || t == "Closed") t else "$t · " +
            java.time.LocalDate.parse(d.deadline).format(java.time.format.DateTimeFormatter.ofPattern("MMM d", java.util.Locale.US)),
            if (urgent) Tone.Red else Tone.Gray) }
        when (d.proof_needed) { 0 -> Badge("No proof needed", Tone.Green); 1 -> Badge("Proof needed", Tone.Amber) }
        if (d.states.isNotEmpty()) Badge(d.states.joinToString() + " only", Tone.Gray)
    }
}

@Composable
fun Section(title: String, body: @Composable () -> Unit) = Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp),
    colors = CardDefaults.cardColors(MaterialTheme.colorScheme.surfaceContainer)) {
    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        body()
    }
}
