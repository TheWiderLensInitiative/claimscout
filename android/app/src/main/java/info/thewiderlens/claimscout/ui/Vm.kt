package info.thewiderlens.claimscout.ui

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import info.thewiderlens.claimscout.BuildConfig
import info.thewiderlens.claimscout.ClaimScoutApp
import info.thewiderlens.claimscout.data.Api
import info.thewiderlens.claimscout.data.ApiException
import info.thewiderlens.claimscout.data.Claim
import info.thewiderlens.claimscout.data.Detail
import info.thewiderlens.claimscout.data.MailAccount
import info.thewiderlens.claimscout.data.Pairing
import info.thewiderlens.claimscout.data.Payout
import info.thewiderlens.claimscout.data.Profile
import info.thewiderlens.claimscout.data.QItem
import info.thewiderlens.claimscout.data.Questionnaire
import info.thewiderlens.claimscout.data.Row
import info.thewiderlens.claimscout.data.Status
import info.thewiderlens.claimscout.data.parsePairLink
import info.thewiderlens.claimscout.mail.Gmail
import info.thewiderlens.claimscout.mail.MailSearch
import info.thewiderlens.claimscout.mail.Outlook
import info.thewiderlens.claimscout.mail.PayoutWatch
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** First run walks every step; "update" only asks about settlements that arrived since. */
enum class Step { Welcome, HomeState, PastStates, Pick, Ask, Email, Notify, Done }

enum class Tab(val label: String, val view: String) { Matches("For you", "matches"), Browse("Browse", "all"), Claims("My claims", "claimed"), Settings("Settings", "") }

class Vm(app: Application) : AndroidViewModel(app) {
    val store = (app as ClaimScoutApp).store
    val pairing = store.pairingFlow.stateIn(viewModelScope, SharingStarted.Eagerly, null)
    val accounts = store.accountsFlow.stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())
    val onboarded = store.onboardedFlow.stateIn(viewModelScope, SharingStarted.Eagerly, true)
    var loaded by mutableStateOf(false)

    var tab by mutableStateOf(Tab.Matches)
    var rows by mutableStateOf<List<Row>>(emptyList())
    var status by mutableStateOf<Status?>(null)
    var query by mutableStateOf("")
    var noProofOnly by mutableStateOf(false)
    var category by mutableStateOf("")
    var sortByPay by mutableStateOf(false)
    var detail by mutableStateOf<Detail?>(null)
    var openId by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var proofNote by mutableStateOf<String?>(null)
    var findingProof by mutableStateOf(false)
    var profile by mutableStateOf<Profile?>(null)
    var payouts by mutableStateOf<List<Payout>>(emptyList())
    var payoutNote by mutableStateOf<String?>(null)
    var checkingPayouts by mutableStateOf(false)
    val payoutCheck = store.payoutCheckFlow.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    // questionnaire
    var quizActive by mutableStateOf(false)
    var quizFull by mutableStateOf(true)
    var step by mutableStateOf(Step.Welcome)
    var quiz by mutableStateOf<Questionnaire?>(null)
    var homeState by mutableStateOf("")
    var pastStates by mutableStateOf(setOf<String>())
    var groupIndex by mutableStateOf(0)
    var picked by mutableStateOf(setOf<String>())        // ids picked on the current chip page
    var toAsk by mutableStateOf(listOf<QItem>())          // picked items still waiting for their yes/no
    var yesCount by mutableStateOf(0)

    // Outlook sign-in in progress
    var outlookCode by mutableStateOf<Outlook.DeviceCode?>(null)
    var msClientId by mutableStateOf(BuildConfig.MS_CLIENT_ID)
    var askedForMsId by mutableStateOf(false)   // show the client-ID box only after "Add Outlook" needed it

    init {
        viewModelScope.launch {
            if (msClientId.isEmpty()) msClientId = store.msClientId()
            loaded = true
            if (store.pairing() != null) {
                reload()
                if (!store.onboardedFlow.first()) startQuiz(full = true)
            }
        }
    }

    suspend fun apiOrNull(): Api? = store.pairing()?.let { p -> Api(p) }

    private suspend fun api(): Api {
        val p = store.pairing() ?: throw ApiException("Not paired")
        return Api(p) { good -> store.setPairing(p.copy(lastGood = good)) }
    }

    private fun launch(block: suspend () -> Unit): Job = viewModelScope.launch {
        busy = true; error = null
        try { block() } catch (e: Exception) {
            error = e.message ?: e.toString()
            if (e is ApiException && e.code == 401) store.setPairing(null)
        } finally { busy = false }
    }

    fun pair(link: String): Boolean {
        val p: Pairing = parsePairLink(link) ?: run { error = "That isn't a ClaimScout pairing link."; return false }
        launch {
            Api(p).status()   // proves the token and certificate before saving
            store.setPairing(p)
            reload()
            if (!store.onboardedFlow.first()) startQuiz(full = true)
        }
        return true
    }

    fun unpair() = launch { store.setPairing(null); rows = emptyList(); status = null }

    fun reload() = launch {
        val a = api()
        status = a.status()
        if (tab == Tab.Claims || tab == Tab.Matches) payouts = a.payouts()
        rows = when (tab) {
            Tab.Settings -> rows
            Tab.Browse -> a.settlements(if (noProofOnly) "noproof" else "all", query, category)
            else -> a.settlements(tab.view)
        }
    }

    fun select(t: Tab) {
        tab = t
        if (t == Tab.Settings) loadProfile() else reload()
    }

    fun open(id: String?) {
        openId = id; detail = null; proofNote = null
        if (id != null) launch { detail = api().detail(id) }
    }

    fun refreshDetail() = openId?.let { id -> launch { detail = api().detail(id) } }

    fun dismiss(id: String) = launch { api().dismiss(id); open(null); reload() }
    fun recheck(id: String) = launch { api().rematch(id); detail = api().detail(id) }

    fun saveClaim(id: String, c: Claim?) = launch {
        if (c == null) api().deleteClaim(id) else api().saveClaim(id, c)
        detail = api().detail(id)
        reload()   // a filed claim leaves For you and shows up under My claims
    }

    fun deleteProof(pid: Long) = launch { api().deleteProof(pid); refreshDetail() }

    /** Search this phone's connected inboxes with the settlement's plan; the PC keeps what proves something. */
    fun findProof() {
        val d = detail ?: return
        val plan = d.proof_plan
        if (accounts.value.isEmpty()) { proofNote = "Connect Gmail or Outlook in Settings first."; return }
        if (plan == null || (plan.senders.isEmpty() && plan.keywords.isEmpty())) {
            proofNote = "There's nothing to search email for on this one."; return
        }
        findingProof = true
        launch {
            try {
                val r = MailSearch(store).run(plan)
                val result = if (r.messages.isEmpty()) "No matching emails in ${r.searched.joinToString()}." else {
                    val kept = api().addProof(d.id, r.messages)
                    "Checked ${r.messages.size} email(s); ${kept.size} look like proof."
                }
                proofNote = (listOf(result) + r.errors).joinToString("\n")
                detail = api().detail(d.id)
            } finally { findingProof = false }
        }
    }

    fun loadProfile() = launch { profile = api().profile() }
    fun saveProfile(p: Profile) = launch { api().saveProfile(p); profile = p; status = api().status() }
    fun checkNow() = launch { api().refresh() }

    fun addGmail(address: String, appPassword: String, done: () -> Unit) = launch {
        Gmail.verify(address.trim(), appPassword)
        store.saveAccount(MailAccount("gmail", address.trim(), appPassword.replace(" ", "")))
        done()
    }

    fun startOutlook() = launch {
        if (msClientId.isBlank()) { askedForMsId = true; throw IllegalStateException("Paste your Microsoft app's client ID first (see the help link).") }
        store.setMsClientId(msClientId)
        val dc = Outlook.start(msClientId.trim())
        outlookCode = dc
        try {
            store.saveAccount(Outlook.finish(msClientId.trim(), dc))
        } finally { outlookCode = null }
    }

    fun removeAccount(a: MailAccount) = launch { store.removeAccount(a) }

    // --- payout watcher ----------------------------------------------------------------------------------------

    /** Search the inboxes (Spam too) for payout emails now, instead of waiting for the next background check. */
    fun checkPayouts() {
        if (accounts.value.isEmpty()) { payoutNote = "Connect Gmail or Outlook in Settings first."; return }
        checkingPayouts = true
        launch {
            try {
                val r = PayoutWatch(store, api()).run()
                val waiting = r.new.count { it.needs_action }
                payoutNote = (listOf(when {
                    waiting > 0 -> "Found $waiting payment${if (waiting == 1) "" else "s"} waiting for you."
                    r.new.isNotEmpty() -> "Found ${r.new.size} settlement email${if (r.new.size == 1) "" else "s"}, nothing to act on."
                    else -> "Checked ${r.searched} settlement email${if (r.searched == 1) "" else "s"}; nothing new."
                }) + r.errors).joinToString("\n")
                payouts = api().payouts()
                status = api().status()
            } finally { checkingPayouts = false }
        }
    }

    fun setPayoutStatus(p: Payout, s: String) = launch {
        api().payoutStatus(p.id, s)
        payouts = api().payouts()
        status = api().status()
    }

    // --- questionnaire ---------------------------------------------------------------------------------------

    /** full = first run (welcome, states, questions, email, notifications); otherwise just the new questions. */
    fun startQuiz(full: Boolean, redo: Boolean = false) {
        quizFull = full; quizActive = true; groupIndex = 0; picked = emptySet(); toAsk = emptyList(); yesCount = 0
        step = if (full) Step.Welcome else Step.Pick
        launch {
            if (redo) api().resetAnswers()
            val p = api().profile()
            homeState = p.states.firstOrNull() ?: ""
            pastStates = p.past_states.toSet()
            if (!full) loadQuiz()
        }
    }

    private suspend fun loadQuiz() {
        quiz = api().questionnaire()
        groupIndex = 0; picked = emptySet()
        if ((quiz?.count ?: 0) == 0) afterQuestions()
    }

    fun saveStates() = launch {
        val p = api().profile()
        api().saveProfile(p.copy(states = listOfNotNull(homeState.takeIf { it.isNotBlank() }),
            past_states = pastStates.filter { it != homeState }))
        step = Step.Pick
        loadQuiz()
    }

    fun togglePick(id: String) { picked = if (id in picked) picked - id else picked + id }

    /** Done with one chip page: what wasn't picked is "unused"; what was picked gets its own question next. */
    fun finishGroup() {
        val g = quiz?.groups?.getOrNull(groupIndex) ?: return
        val unused = g.items.filter { it.id !in picked }.associate { it.id to "unused" }
        toAsk = g.items.filter { it.id in picked }
        picked = emptySet()
        launch {
            if (unused.isNotEmpty()) status = api().answer(unused)
            if (toAsk.isEmpty()) nextGroup() else step = Step.Ask
        }
    }

    fun answer(item: QItem, a: String) {
        toAsk = toAsk.drop(1)
        if (a == "yes") yesCount++
        launch {
            status = api().answer(mapOf(item.id to a), if (a != "no") listOf(item.label) else emptyList())
            if (toAsk.isEmpty()) nextGroup()
        }
    }

    private suspend fun nextGroup() {
        val groups = quiz?.groups ?: emptyList()
        if (groupIndex + 1 < groups.size) { groupIndex++; step = Step.Pick } else afterQuestions()
    }

    private suspend fun afterQuestions() {
        status = api().status()
        step = if (quizFull) Step.Email else Step.Done
    }

    /** Leave the rest for later (first run still goes on to email and notifications). */
    fun skipQuestions() = launch { afterQuestions() }

    fun nextFromEmail() { step = Step.Notify }
    fun nextFromNotify() { step = Step.Done }

    fun finishQuiz() = launch {
        store.setOnboarded(true)
        quizActive = false
        tab = Tab.Matches
        reload()
    }
}
